from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from django.utils import timezone


class Organization(models.Model):
    """A relief body that claims and works on cases.

    Report §3.6 ERD: organization.
    """

    class Type(models.TextChoices):
        NGO = "ngo", "NGO"
        AGENCY = "agency", "Government agency"
        VOLUNTEER_GROUP = "volunteer_group", "Volunteer group"

    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=Type)
    contact_no = models.CharField(max_length=20)
    service_area = models.CharField(max_length=255)

    class Meta:
        db_table = "organization"

    def __str__(self):
        return self.name


class UserAccountManager(BaseUserManager):
    """Django's default manager assumes a `username` field, which this model
    has not got, so `createsuperuser` needs its own path in here."""

    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        # Lowercases the domain, so Ali@GMAIL.com and ali@gmail.com collide
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, **extra_fields)
        user.set_password(password)  # hashes; the raw password is never stored
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", UserAccount.Role.SYSTEM_ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self.create_user(email, full_name, password, **extra_fields)


class UserAccount(AbstractBaseUser, PermissionsMixin):
    """Shared base account for all four roles.

    Report §3.6 ERD: user_account. `password_hash` in the ERD is the
    `password` field inherited from AbstractBaseUser.
    """

    class Role(models.TextChoices):
        COMMUNITY_MEMBER = "community_member", "Community member"
        DISASTER_OFFICER = "disaster_officer", "Disaster officer"
        NGO_VOLUNTEER = "ngo_volunteer", "NGO volunteer"
        SYSTEM_ADMIN = "system_admin", "System administrator"

    class VerificationStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    # What the account may actually do. Applications never write here — an
    # admin copies requested_role across on approval (ADR-012).
    role = models.CharField(
        max_length=20, choices=Role, default=Role.COMMUNITY_MEMBER
    )
    # What was asked for. Holding it apart from `role` is what stops a form
    # submission granting its own privileges.
    requested_role = models.CharField(
        max_length=20, choices=Role, null=True, blank=True
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus,
        default=VerificationStatus.NOT_REQUIRED,
    )
    verified_by_user = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_accounts",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_note = models.TextField(blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="members",
    )

    email = models.EmailField(max_length=150, unique=True)
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # gates access to /admin

    objects = UserAccountManager()

    USERNAME_FIELD = "email"  # log in with email, not username
    REQUIRED_FIELDS = ["full_name"]  # extra prompts for createsuperuser

    class Meta:
        db_table = "user_account"

    def __str__(self):
        return self.email

    def approve_application(self,admin,note=""):

        if self.verification_status != self.VerificationStatus.PENDING:
            raise ValueError('only a pending application can be approved')

        self.role = self.requested_role
        self.verification_status = self.VerificationStatus.VERIFIED
        self.verified_by_user    = admin
        self.verified_at         = timezone.now()
        self.verification_note   = note

        self.save(update_fields=["role","verification_status","verified_by_user","verified_at","verification_note"])

    def reject_application(self,admin,note=""):

        if self.verification_status != self.VerificationStatus.PENDING:
            raise ValueError('only a pending application can be approved')

        if not note:
            raise ValueError('a rejection must give a reason')


        self.verification_status = self.VerificationStatus.REJECTED
        self.verified_by_user    = admin
        self.verified_at         = timezone.now()
        self.verification_note   = note

        self.save(update_fields=["verification_status","verified_by_user","verified_at","verification_note"])

    def revoke_approval(self,admin,note=""):

        if self.verification_status != self.VerificationStatus.VERIFIED:
            raise ValueError('only an approved account can be revoked')

        if not note:
            raise ValueError('a revocation must give a reason')

        self.role = self.Role.COMMUNITY_MEMBER


        self.verification_status = self.VerificationStatus.REJECTED
        self.verified_by_user    = admin
        self.verified_at         = timezone.now()
        self.verification_note   = note

        self.save(update_fields=["role", "verification_status","verified_by_user","verified_at","verification_note"])



class RegistrationDocument(models.Model):
    """Evidence attached to a role application — organisation registration,
    staff ID, authorisation letter (ADR-012).

    A table rather than a column because an application carries several files,
    the same shape as case_photo.
    """

    user = models.ForeignKey(
        "UserAccount", on_delete=models.CASCADE, related_name="registration_documents"
    )
    file = models.FileField(upload_to="registration/%Y/%m/")
    label = models.CharField(max_length=120)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "registration_document"
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"{self.label} — {self.user.email}"


class VolunteerProfile(models.Model):
    """A community member who has also registered to volunteer.

    Report §3.6 ERD: volunteer_profile. IC documents are verified by an admin
    during registration review (GAPS A5), hence `verified_by_user`.
    Dormant: the channel was withdrawn on 23 Sep 2026; the table stays as migration history.
    """

    user = models.OneToOneField(
        "UserAccount", on_delete=models.CASCADE, primary_key=True,
        related_name="volunteer_profile",
    )
    skills = models.TextField(blank=True)
    availability = models.CharField(max_length=100, blank=True)
    vehicle_access = models.BooleanField(default=False)
    ic_document_ref = models.CharField(max_length=50, null=True, blank=True)
    verified_by_user = models.ForeignKey(
        "UserAccount", on_delete=models.PROTECT, null=True, blank=True,
        related_name="verified_volunteers",
    )

    class Meta:
        db_table = "volunteer_profile"

    def __str__(self):
        return f"Volunteer: {self.user.full_name}"


class RoleApplication(UserAccount):
    """The same rows as UserAccount, shown as a review queue.

    A proxy adds no table and no columns — it exists so the admin can offer a
    second screen over the same data: the account form is for editing a person,
    this one is for deciding an application, and the two want very different
    fields on screen.
    """

    class Meta:
        proxy = True
        verbose_name = "role application"
        verbose_name_plural = "role applications"

    def __str__(self):
        return f"{self.full_name} — {self.get_requested_role_display()}"
