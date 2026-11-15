from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from bookings import clock

from accounts.models import User, WorkerProfile
from .models import JobAssignment, LaundryOrder


@transaction.atomic
def accept_order(user_id, order_id):
  user = User.objects.select_for_update().get(pk=user_id)
  profile = (
    WorkerProfile.objects
    .select_for_update()
    .filter(user=user)
    .first()
  )
  if profile is None:
    raise ValidationError("You do not have a worker profile.")

  if not profile.can_accept_jobs():
    raise ValidationError(
      "You must be approved and available to accept tasks."
    )

  order = get_object_or_404(
    LaundryOrder.objects.select_for_update(),
    pk=order_id,
    quote__residence_id=profile.residence_id,
  )
  quote = order.quote

  if (
    order.status != "requested"
    or JobAssignment.objects.filter(order=order).exists()
  ):
    raise ValidationError("This task is no longer available.")

  reservations = list(
    order.reservations
    .select_for_update()
    .select_related("machine__laundry_room__residence")
    .filter(status="reserved")
  )

  if len(reservations) != 2:
    raise ValidationError(
      "This order does not have a valid reserved machine pair."
    )

  machine_types = {
    reservation.machine.machine_type
    for reservation in reservations
  }
  room_ids = {
    reservation.machine.laundry_room_id
    for reservation in reservations
  }

  if machine_types != {"washer", "dryer"} or len(room_ids) != 1:
    raise ValidationError("The reserved machine pair is invalid.")

  for reservation in reservations:
    machine = reservation.machine
    room = machine.laundry_room

    if (
      reservation.service_date != quote.service_date
      or reservation.window_start != quote.window_start
      or room.residence_id != quote.residence_id
      or room.block != quote.block
      or not room.residence.is_active
      or not room.is_active
      or machine.status != "ACTIVE"
    ):
      raise ValidationError(
        "The reserved machines are no longer suitable."
      )

  if quote.service_start <= clock.now():
    raise ValidationError("This pickup window has already started.")

  updated = (
    LaundryOrder.objects
    .filter(
      pk=order.pk,
      status="requested",
      assignment__isnull=True,
    )
    .update(status="confirmed")
  )
  if updated != 1:
    raise ValidationError("This task is no longer available.")

  return JobAssignment.objects.create(
    order=order,
    worker=profile,
    agreed_payout=quote.worker_fee,
  )