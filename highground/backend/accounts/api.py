"""Session-authenticated auth endpoints (ADR-001: sessions, not JWT)."""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Organization, RegistrationDocument, UserAccount


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    organization = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
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
def login_view(request):
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""

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

    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# Applying for system_admin is not offered. A platform administrator is
# provisioned, never applied for — an approval flow that can mint admins is one
# social-engineered click away from handing over the platform (ADR-012).
APPLICABLE_ROLES = [
    UserAccount.Role.DISASTER_OFFICER,
    UserAccount.Role.NGO_VOLUNTEER,
]


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

    def validate_email(self, value):
        value = value.strip().lower()
        if UserAccount.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

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


MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}


@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def register(request):
    """Create an account, and record a role application if one was made.

    Everyone is created as community_member. Applying for anything else stores
    the request in `requested_role` and leaves the account least-privileged
    until an admin approves it (ADR-012).
    """
    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    requested_role = data.get("requested_role") or None
    documents = request.FILES.getlist("documents")

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
        if upload.content_type not in ALLOWED_DOCUMENT_TYPES:
            return Response(
                {"documents": [f"{upload.name} must be a PDF, JPEG or PNG."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        )

        for upload in documents:
            RegistrationDocument.objects.create(
                user=user, file=upload, label=upload.name[:120]
            )

    login(request, user)
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


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
