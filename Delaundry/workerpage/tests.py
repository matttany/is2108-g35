from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import (
  IntegrityError,
  OperationalError,
  close_old_connections,
  connections,
)
from django.db.models.query import QuerySet
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, WorkerProfile
from bookings.acceptance import accept_order
from bookings.models import (
  JobAssignment,
  LaundryOrder,
  MachineReservation,
  PriceQuote,
)
from facilities.models import LaundryRoom, Machine, Residence


class AcceptanceTests(TransactionTestCase):
  def setUp(self):
    hall, _ = Residence.objects.get_or_create(
      name="temasek",
      defaults={"is_active": True},
    )
    room, _ = LaundryRoom.objects.get_or_create(
      residence=hall,
      block="A",
      defaults={"is_active": True},
    )
    self.workers = []

    for number in [1, 2]:
      user = User.objects.create_user(
        username=f"p03worker{number}",
        email=f"p03worker{number}@example.com",
        name=f"Worker {number}",
        role="worker",
      )
      WorkerProfile.objects.create(
        user=user,
        residence=hall,
        approval_status="approved",
        is_available=True,
      )
      self.workers.append(user)

    customer = User.objects.create_user(
      username="p03customer",
      email="p03customer@example.com",
      name="Test Customer",
      role="customer",
    )
    quote = PriceQuote.objects.create(
      customer=customer,
      residence=hall,
      block="A",
      unit_number="#01-01",
      service_date=timezone.localdate() + timedelta(days=1),
      window_start=time(14),
      expires_at=timezone.now() + timedelta(minutes=10),
      machine_fee=Decimal("2.00"),
      worker_fee=Decimal("1.00"),
      platform_fee=Decimal("1.00"),
      total=Decimal("4.00"),
      multiplier=Decimal("1.00"),
      reference_capacity=1,
    )
    self.order = LaundryOrder.objects.create(quote=quote)

    for machine_type, code in [("washer", "W01"), ("dryer", "D01")]:
      machine, _ = Machine.objects.get_or_create(
        laundry_room=room,
        code=code,
        defaults={
          "machine_type": machine_type,
          "status": "ACTIVE",
        },
      )
      MachineReservation.objects.create(
        order=self.order,
        machine=machine,
        service_date=quote.service_date,
        window_start=quote.window_start,
      )

    self.accept_url = reverse(
      "workerpage:accept_task",
      args=[self.order.pk],
    )
    self.board_url = reverse("workerpage:task_board")

  def test_get_and_missing_csrf_are_rejected(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.workers[0])

    self.assertEqual(client.get(self.accept_url).status_code, 405)
    self.assertEqual(client.post(self.accept_url).status_code, 403)

    self.order.refresh_from_db()
    self.assertEqual(self.order.status, "requested")
    self.assertFalse(JobAssignment.objects.filter(order=self.order).exists())
    self.assertEqual(self.order.reservations.count(), 2)

  def test_valid_post_confirms_and_reuses_reservations(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.workers[0])

    original_ids = set(
      self.order.reservations.values_list("pk", flat=True)
    )
    client.get(self.board_url)
    token = client.cookies["csrftoken"].value

    response = client.post(
      self.accept_url,
      {"csrfmiddlewaretoken": token},
      follow=True,
    )

    self.assertRedirects(response, self.board_url)
    self.assertContains(
      response,
      f"Order #{self.order.pk} accepted. Agreed payout: S$1.00.",
    )
    self.assertNotContains(response, f"Order #{self.order.pk}</h2>")

    self.order.refresh_from_db()
    self.assertEqual(self.order.status, "confirmed")
    assignment = JobAssignment.objects.get(order=self.order)
    self.assertEqual(assignment.worker.user_id, self.workers[0].pk)
    self.assertEqual(assignment.agreed_payout, Decimal("1.00"))
    self.assertEqual(
      set(self.order.reservations.values_list("pk", flat=True)),
      original_ids,
    )
    self.assertEqual(MachineReservation.objects.count(), 2)

  def test_board_displays_reserved_pair(self):
    self.client.force_login(self.workers[0])

    response = self.client.get(self.board_url)

    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "Reserved machines")
    self.assertContains(response, "Washer W01")
    self.assertContains(response, "Dryer D01")
    self.assertContains(response, "Block A")

  def test_board_hides_released_reservations(self):
    washer = self.order.reservations.get(machine__machine_type="washer")
    washer.status = "released"
    washer.save(update_fields=["status"])

    self.client.force_login(self.workers[0])
    response = self.client.get(self.board_url)

    self.assertEqual(response.status_code, 200)
    self.assertNotContains(response, "Washer W01")
    self.assertContains(response, "Dryer D01")

  def test_competing_acceptance(self):
    barrier = Barrier(2)
    original_update = QuerySet.update

    # Both requests reach the confirmation attempt before either proceeds.
    def synchronised_update(queryset, **kwargs):
      if queryset.model is LaundryOrder and kwargs.get("status") == "confirmed":
        barrier.wait(timeout=15)
      return original_update(queryset, **kwargs)

    order_id = self.order.pk

    def attempt(user_id):
      close_old_connections()
      try:
        assignment = accept_order(user_id, order_id)
        return ("accepted", assignment.pk)
      except ValidationError:
        return ("unavailable", None)
      except IntegrityError:
        return ("conflict", None)
      except OperationalError as error:
        if "locked" not in str(error).lower():
          raise
        return ("locked", None)
      finally:
        connections.close_all()

    with patch.object(QuerySet, "update", synchronised_update):
      with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
          executor.map(attempt, [user.pk for user in self.workers])
        )

    successes = sum(result[0] == "accepted" for result in results)
    self.assertLessEqual(successes, 1)
    self.assertEqual(
      JobAssignment.objects.filter(order=self.order).count(),
      successes,
    )

    # SQLite may reject both competing writes. A later retry must work.
    if successes == 0:
      self.order.refresh_from_db()
      self.assertEqual(self.order.status, "requested")
      accept_order(self.workers[0].pk, self.order.pk)

    self.order.refresh_from_db()
    self.assertEqual(self.order.status, "confirmed")
    self.assertEqual(
      JobAssignment.objects.filter(order=self.order).count(),
      1,
    )
    self.assertEqual(MachineReservation.objects.count(), 2)

    with self.assertRaises(ValidationError):
      accept_order(self.workers[1].pk, self.order.pk)
