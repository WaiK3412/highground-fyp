"""Session-authenticated auth endpoints (ADR-001: sessions, not JWT)."""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .mail import send_account_exists_email, send_confirmation_email
from .models import Organization, RegistrationDocument, UserAccount
from .two_factor import confirmed_device, requires_two_factor, start_pending
from cases.images import UnreadableImage, clean_photo, generated_name
from cases.upload_validation import has_expected_signature


class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        # Function views have no throttle_scope. A fixed class scope also
        # keeps authenticated and anonymous attempts on the same IP counter.
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RegisterRateThrottle(LoginRateThrottle):
    scope = "register"


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    organization = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    # An officer's district (ADR-024), so the sidebar can show whose cases these are.
    district = serializers.CharField(source="district.name", read_only=True, default=None)
    # The SPA needs these to show an applicant where their application stands.
    verification_status = serializers.CharField(read_only=True)
    requested_role = serializers.CharField(read_only=True, default=None)
    requested_role_display = serializers.CharField(
        source="get_requested_role_display", read_only=True, default=None
    )
    verification_note = serializers.CharField(read_only=True)


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Hand the SPA a CSRF cookie before it attempts its first POST."""
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    credentials = LoginSerializer(data=request.data)
    credentials.is_valid(raise_exception=True)
    email = credentials.validated_data["email"].strip().lower()
    password = credentials.validated_data["password"]

    user = authenticate(request, username=email, password=password)
    if user is None:
        # Vague on purpose — never confirm whether an address is registered.
        return Response(
            {"detail": "Email or password is incorrect."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        return Response(
            {"detail": "This account has been deactivated."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not user.email_confirmed:
        # Only someone who knows the password learns the account exists.
        return Response(
            {
                "detail": "Confirm your email address first. We can send the link again.",
                "code": "email_unconfirmed",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if requires_two_factor(user):
        # Not signed in yet: the session only remembers who is half-way (ADR-026).
        start_pending(request, user)
        return Response({"two_factor": "verify" if confirmed_device(user) else "setup"})

    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileSerializer(serializers.Serializer):
    """The only account fields a user may change themselves (FR2).

    Not email (the login identity) and never role (ADR-012: an admin grants it).
    """

    full_name = serializers.CharField(max_length=100, required=False)
    phone = serializers.CharField(max_length=20, required=False)

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter your name.")
        return value

    def validate_phone(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a phone number.")
        return value


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        serializer = ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(request.user, field, value)
        if serializer.validated_data:
            request.user.save(update_fields=list(serializer.validated_data))
    return Response(UserSerializer(request.user).data)


# Applying for system_admin is not offered. A platform administrator is
# provisioned, never applied for — an approval flow that can mint admins is one
# social-engineered click away from handing over the platform (ADR-012).
APPLICABLE_ROLES = [
    UserAccount.Role.DISASTER_OFFICER,
    UserAccount.Role.NGO_VOLUNTEER,
]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


def _public_csrf_rejection(request):
    """DRF exempts API views from middleware CSRF checks for anonymous users."""
    return CsrfViewMiddleware(lambda raw_request: None).process_view(
        request._request, lambda raw_request: None, (), {}
    )


class RegistrationSerializer(serializers.Serializer):
    """Self-registration for any role (ADR-012).

    `requested_role` is accepted; `role` is not, and never will be. The
    difference is the whole design: this field records an application, the
    view grants community_member regardless, and only an admin calling
    approve_application() copies one into the other.
    """

    full_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=150)
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    requested_role = serializers.ChoiceField(
        choices=APPLICABLE_ROLES, required=False, allow_blank=True
    )
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )
    # The terms of use and the privacy notice: required, and checked here
    # because a checkbox in the browser alone proves nothing.
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError(
                "Agree to the terms of use and the privacy notice to create an account."
            )
        return value

    def validate_email(self, value):
        # No "already registered" error: that would tell anyone which addresses
        # have accounts. register() handles a taken address by email instead.
        return value.strip().lower()

    def validate(self, attrs):
        # Re-checked here as well as in the form: the endpoint is public, so a
        # client-side check alone guarantees nothing.
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "The two passwords do not match."}
            )
        return attrs

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


CHECK_EMAIL = {"detail": "Check your email to confirm your account."}
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_DOCUMENTS = 5
ALLOWED_DOCUMENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}


@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([RegisterRateThrottle])
def register(request):
    """Create an account, and record a role application if one was made.

    Everyone is created as community_member. Applying for anything else stores
    the request in `requested_role` and leaves the account least-privileged
    until an admin approves it (ADR-012). The account cannot sign in until its
    email address is confirmed (ADR-026).
    """
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    requested_role = data.get("requested_role") or None
    documents = request.FILES.getlist("documents")

    if len(documents) > MAX_DOCUMENTS:
        return Response(
            {"documents": [f"Attach at most {MAX_DOCUMENTS} documents."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Evidence is the point of the review; without it there is nothing to check.
    if requested_role and not documents:
        return Response(
            {"documents": ["Applying for this role requires supporting documents."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    for upload in documents:
        if upload.size > MAX_DOCUMENT_BYTES:
            return Response(
                {"documents": [f"{upload.name} is larger than 5 MB."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.content_type not in ALLOWED_DOCUMENT_TYPES or not has_expected_signature(upload):
            return Response(
                {"documents": [f"{upload.name} must be a PDF, JPEG or PNG."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Decode every image before creating an account or storing any evidence.
    # PDF content is retained; only its storage name is generated (ADR-023).
    prepared_documents = []
    try:
        for upload in documents:
            label = upload.name[:120]
            if upload.content_type.startswith("image/"):
                stored_file = clean_photo(upload)
            else:
                upload.name = generated_name(upload)
                stored_file = upload
            prepared_documents.append((stored_file, label))
    except UnreadableImage as exc:
        return Response({"documents": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

    # Same answer for a new and a taken address (ADR-026); only the email differs.
    existing = UserAccount.objects.filter(email__iexact=data["email"]).first()
    if existing is not None:
        send_account_exists_email(existing)  # the uploaded documents are discarded
        return Response(CHECK_EMAIL, status=status.HTTP_202_ACCEPTED)

    try:
        user = _create_applicant(data, requested_role, prepared_documents)
    except IntegrityError:
        # Registered by a simultaneous request a moment ago: the same as taken.
        return Response(CHECK_EMAIL, status=status.HTTP_202_ACCEPTED)
    send_confirmation_email(user)
    return Response(CHECK_EMAIL, status=status.HTTP_202_ACCEPTED)


def _create_applicant(data, requested_role, prepared_documents):
    """The new, unconfirmed account and any role-application evidence, saved together."""
    with transaction.atomic():
        user = UserAccount.objects.create_user(
            email=data["email"],
            full_name=data["full_name"],
            password=data["password"],
            phone=data["phone"],
            # The one line that matters: the granted role is decided here, not
            # by the request. An applicant is a resident until an admin says
            # otherwise.
            role=UserAccount.Role.COMMUNITY_MEMBER,
            requested_role=requested_role,
            organization=data.get("organization") if requested_role else None,
            verification_status=(
                UserAccount.VerificationStatus.PENDING
                if requested_role
                else UserAccount.VerificationStatus.NOT_REQUIRED
            ),
            email_confirmed=False,
            consent_at=timezone.now(),
        )

        for upload, label in prepared_documents:
            RegistrationDocument.objects.create(
                user=user, file=upload, label=label
            )
    return user


class OrganizationSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)


@api_view(["GET"])
@permission_classes([AllowAny])
def organizations(request):
    """Public list for the registration form's organisation picker.

    Deliberately thin: name and type only. Contact numbers and service areas
    are not an applicant's business before they have been verified.
    """
    return Response(
        OrganizationSerializer(Organization.objects.order_by("name"), many=True).data
    )
