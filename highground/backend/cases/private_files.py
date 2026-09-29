"""Authenticated access to uploaded household and applicant evidence."""

import mimetypes
from pathlib import Path

from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import RegistrationDocument, UserAccount
from accounts.permissions import may_see_private_case_details, visible_cases

from .models import CasePhoto, CaseRecord


def _file_response(field, *, attachment, inline_image=False):
    try:
        handle = field.open("rb")
    except (OSError, ValueError):
        return Response({"detail": "Not found."}, status=404)
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    if inline_image and content_type not in {"image/jpeg", "image/png", "image/webp"}:
        content_type = "application/octet-stream"
        attachment = True
    response = FileResponse(
        handle, as_attachment=attachment, filename=Path(field.name).name,
        content_type=content_type,
    )
    response["Cache-Control"] = "private, no-store"
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def case_photo(request, pk):
    photo = CasePhoto.objects.select_related("case").filter(pk=pk).first()
    if photo is None:
        return Response({"detail": "Not found."}, status=404)
    case = visible_cases(request.user, CaseRecord.objects.filter(pk=photo.case_id)).first()
    if case is None or not may_see_private_case_details(request.user, case):
        return Response({"detail": "Not found."}, status=404)
    return _file_response(photo.file_path, attachment=False, inline_image=True)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def registration_document(request, pk):
    if request.user.role != UserAccount.Role.SYSTEM_ADMIN or not request.user.is_staff:
        return Response({"detail": "Not found."}, status=404)
    document = RegistrationDocument.objects.filter(pk=pk).first()
    if document is None:
        return Response({"detail": "Not found."}, status=404)
    return _file_response(document.file, attachment=True)
