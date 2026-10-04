"""Closure must not be undone by an edit that read an older open appeal."""

from datetime import timedelta
import threading
from unittest.mock import patch

from django.db import connection, transaction
from django.test import Client, TransactionTestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.serializers.appeals import SupplyAppealSerializer
from cases.models import DropOffPoint, SupplyAppeal
from .race_helpers import GazetteerReloadMixin


class AppealClosureRaceTests(GazetteerReloadMixin, TransactionTestCase):
    def test_edit_waits_for_closure_and_cannot_reopen_the_appeal(self):
        org = Organization.objects.create(name="Test NGO", type=Organization.Type.NGO)
        user = UserAccount.objects.create_user(
            email="ngo@example.my", full_name="NGO responder",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=org,
        )
        point = DropOffPoint.objects.create(name="Test hall", address="Jalan Test", area="Test")
        appeal = SupplyAppeal.objects.create(
            organization=org, created_by_user=user, drop_off_point=point,
            title="Water", items="Bottled water",
            needed_until=timezone.localdate() + timedelta(days=1),
        )
        validation_started = threading.Event()
        original_validate = SupplyAppealSerializer.validate_items
        results, errors = [], []

        def validate(serializer, value):
            validation_started.set()
            return original_validate(serializer, value)

        def edit():
            try:
                client = Client()
                client.force_login(user)
                results.append(client.patch(
                    f"/api/appeals/{appeal.pk}/", {"items": "Rice"},
                    content_type="application/json",
                ).status_code)
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        # A closure has written but not committed. Without the endpoint's row
        # lock, the edit can read OPEN, then overwrite the closure after commit.
        worker = threading.Thread(target=edit)
        with patch.object(SupplyAppealSerializer, "validate_items", validate):
            with transaction.atomic():
                closing = SupplyAppeal.objects.select_for_update().get(pk=appeal.pk)
                closing.status = SupplyAppeal.Status.CLOSED
                closing.closed_at = timezone.now()
                closing.save(update_fields=["status", "closed_at"])
                worker.start()
                # Unlocked requests reach validation; locked ones wait until
                # closure commits, then reject the edit without validating it.
                validation_started.wait(timeout=1)
            worker.join(timeout=10)

        self.assertFalse(worker.is_alive(), "edit request did not finish")
        self.assertEqual(errors, [])
        self.assertEqual(results, [409])
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, SupplyAppeal.Status.CLOSED)
        self.assertEqual(appeal.items, "Bottled water")
        self.assertIsNotNone(appeal.closed_at)
