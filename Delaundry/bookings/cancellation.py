from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from bookings import clock

from accounts.models import User
from .models import DeliveryProof, JobAssignment, LaundryOrder


def cancellation_error(order, assignment):
  if order.status not in ["requested", "confirmed"]:
    return "Only requested or confirmed orders can be cancelled."
  if clock.now() >= order.quote.service_start:
    return "Cancellation closes when the pickup window starts."
  if assignment is not None:
    if (
      assignment.picked_up_at is not None or assignment.out_for_return_at is not None
      or assignment.completed_at is not None or assignment.sessions.exists()
      or DeliveryProof.objects.filter(assignment=assignment).exists()
    ):
      return "This order has already started. Please report a problem if you need help."
  return ""


@transaction.atomic
def cancel_order(user_id, order_id):
  user = User.objects.select_for_update().get(pk=user_id)
  if not user.is_active or user.role != "customer":
    raise ValidationError("An active customer account is required.")
  order = get_object_or_404(
    LaundryOrder.objects.select_for_update(), pk=order_id, quote__customer=user,
  )
  if order.status == "cancelled":
    return order

  # Progress and acceptance also lock the order before changing its records.
  assignment = JobAssignment.objects.filter(order=order).first()
  list(order.reservations.select_for_update().order_by("pk"))
  error = cancellation_error(order, assignment)
  if error:
    raise ValidationError(error)
  now = clock.now()
  if now >= order.quote.service_start:
    raise ValidationError("Cancellation closes when the pickup window starts.")
  changed = LaundryOrder.objects.filter(pk=order.pk, status__in=["requested", "confirmed"]).update(
    status="cancelled", cancelled_at=now,
  )
  if changed != 1:
    raise ValidationError("This order changed. Please refresh and try again.")

  # Keep the rows for history; only future, unused reservations become available.
  local_now = timezone.localtime(now)
  order.reservations.filter(status="reserved").filter(
    Q(service_date__gt=local_now.date())
    | Q(service_date=local_now.date(), window_start__gt=local_now.time()),
  ).update(status="released")
  order.status = "cancelled"
  order.cancelled_at = now
  return order
