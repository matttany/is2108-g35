from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import User, WorkerProfile
from facilities.models import Machine
from .models import JobAssignment, LaundryOrder, MachineReservation, MachineSession


@transaction.atomic
def update_task(user_id, assignment_id, action):
  user = User.objects.select_for_update().get(pk=user_id)
  profile = WorkerProfile.objects.select_for_update().filter(user=user).first()
  if (
    profile is None
    or user.role != "worker"
    or not user.is_active
    or profile.approval_status != "approved"
  ):
    raise ValidationError("An approved worker account is required.")

  assignment = get_object_or_404(
    JobAssignment.objects.select_for_update(),
    pk=assignment_id,
    worker=profile,
  )
  order = LaundryOrder.objects.select_for_update().get(pk=assignment.order_id)
  quote = order.quote
  now = timezone.now()

  if action == "collect":
    if not quote.service_start <= now <= quote.pickup_end:
      raise ValidationError("Record collection within the 15-minute pickup window.")
    changed = LaundryOrder.objects.filter(pk=order.pk, status="confirmed").update(
      status="picked_up",
    )
    if changed != 1 or assignment.picked_up_at is not None:
      raise ValidationError("Collection has already been recorded or is not allowed.")
    assignment.picked_up_at = now
    assignment.save(update_fields=["picked_up_at"])
    return "Collection recorded."

  if action in ["start_wash", "start_dry"]:
    washing = action == "start_wash"
    machine_type = "washer" if washing else "dryer"
    expected_status = "picked_up" if washing else "washing"
    next_status = "washing" if washing else "drying"
    cycle_minutes = Machine.WASH_CYCLE_MINUTES if washing else Machine.DRY_CYCLE_MINUTES
    if order.status != expected_status or assignment.picked_up_at is None:
      raise ValidationError("This task is not ready for that cycle.")
    if not washing:
      washes = list(assignment.sessions.filter(machine__machine_type="washer"))
      if len(washes) != 1 or washes[0].ended_at is None or washes[0].ended_at > now:
        raise ValidationError("Finish the wash before starting the dryer.")
    remaining_cycles = cycle_minutes + (Machine.DRY_CYCLE_MINUTES if washing else 0)
    if now < quote.service_start or now + timedelta(minutes=remaining_cycles) > quote.delivery_by:
      raise ValidationError("There is insufficient time for the remaining cycles before the return deadline.")

    reservations = list(
      MachineReservation.objects.select_for_update()
      .filter(order=order, status="reserved", machine__machine_type=machine_type)
    )
    if len(reservations) != 1:
      raise ValidationError(f"This order needs exactly one reserved {machine_type}.")
    reservation = reservations[0]
    machine = Machine.objects.select_for_update().select_related(
      "laundry_room__residence",
    ).get(pk=reservation.machine_id)
    room = machine.laundry_room
    if (
      machine.status != "ACTIVE"
      or not room.is_active
      or not room.residence.is_active
      or room.residence_id != quote.residence_id
      or room.block != quote.block
      or reservation.service_date != quote.service_date
      or reservation.window_start != quote.window_start
    ):
      raise ValidationError("The reserved machine is not available for this order.")
    if not washing and machine.laundry_room_id != washes[0].machine.laundry_room_id:
      raise ValidationError("The reserved dryer must be in the same room as the washer.")
    if MachineSession.objects.filter(machine=machine, ended_at__isnull=True).exists():
      raise ValidationError("The reserved machine is still in use.")
    if assignment.sessions.filter(machine__machine_type=machine_type).exists():
      raise ValidationError("This cycle has already been recorded for this task.")

    changed = LaundryOrder.objects.filter(pk=order.pk, status=expected_status).update(
      status=next_status,
    )
    if changed != 1:
      raise ValidationError("This task has already changed. Please refresh.")
    MachineSession.objects.create(
      assignment=assignment,
      machine=machine,
      started_at=now,
      expected_end=now + timedelta(minutes=cycle_minutes),
    )
    return f"{'Wash' if washing else 'Drying'} started. Expected duration: {cycle_minutes} minutes."

  if action in ["finish_wash", "finish_dry"]:
    washing = action == "finish_wash"
    machine_type = "washer" if washing else "dryer"
    session = (
      assignment.sessions.select_for_update()
      .filter(machine__machine_type=machine_type, ended_at__isnull=True)
      .first()
    )
    if order.status != ("washing" if washing else "drying") or session is None:
      raise ValidationError("There is no running cycle to finish.")
    if now < session.expected_end:
      raise ValidationError("The 30-minute cycle has not finished yet.")
    changed = MachineSession.objects.filter(pk=session.pk, ended_at__isnull=True).update(
      ended_at=now,
    )
    if changed != 1:
      raise ValidationError("Cycle completion has already been recorded.")
    if not washing:
      changed = LaundryOrder.objects.filter(pk=order.pk, status="drying").update(
        status="out_for_return",
      )
      if changed != 1:
        raise ValidationError("This task has already changed. Please refresh.")
      assignment.out_for_return_at = now
      assignment.save(update_fields=["out_for_return_at"])
      return "Drying completed. Laundry is ready for return."
    return "Wash completion recorded."

  raise ValidationError("Unknown task action.")
