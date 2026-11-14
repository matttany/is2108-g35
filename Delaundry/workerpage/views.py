from django.shortcuts import render

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET

from accounts.models import WorkerProfile


from django.db.models import Prefetch, Q
from django.utils import timezone

from bookings.models import JobAssignment, LaundryOrder, MachineReservation, MachineSession

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from bookings.acceptance import accept_order
from bookings.progress import update_task
# Create your views here.

@login_required(login_url="accounts:worker_login")
@require_GET
def task_board(request):
  if request.user.role != "worker":
    return HttpResponseForbidden("This page is for laundry workers only.")

  profile = (
    WorkerProfile.objects
    .select_related("user", "residence")
    .filter(user=request.user)
    .first()
  )
  if profile is None:
    return HttpResponseForbidden(
      "Your worker profile is missing. Please contact staff."
    )
  if not profile.can_accept_jobs():
    return HttpResponseForbidden(
      "You must be approved and available to browse tasks."
    )

  now = timezone.localtime()

  orders = (
    LaundryOrder.objects
    .filter(
      status="requested",
      quote__residence=profile.residence,
      assignment__isnull=True,
    )
    .exclude(quote__block="")
    .filter(
      Q(quote__service_date__gt=now.date())
      | Q(
        quote__service_date=now.date(),
        quote__window_start__gt=now.time(),
      )
    )
    .select_related("quote__customer", "quote__residence")
    .prefetch_related(
      Prefetch(
        "reservations",
        queryset=(
          MachineReservation.objects
          .filter(status="reserved")
          .select_related("machine__laundry_room")
          .order_by("machine__machine_type", "machine__code")
        ),
        to_attr="reserved_pair",
      )
    )
    .order_by("quote__service_date", "quote__window_start", "created_at")
  )

  return render(
    request,
    "workerpage/task_board.html",
    {"profile": profile,
     "orders": orders},
  )


@login_required(login_url="accounts:worker_login")
@require_GET
def my_tasks(request):
  if request.user.role != "worker":
    return HttpResponseForbidden("This page is for laundry workers only.")

  profile = WorkerProfile.objects.filter(user=request.user).first()
  if profile is None:
    return HttpResponseForbidden(
      "Your worker profile is missing."
    )

  assignments = (
    JobAssignment.objects
    .filter(
      worker=profile,
      order__status__in=[
        "confirmed", "picked_up", "washing", "drying", "out_for_return",
      ],
    )
    .select_related("order__quote__customer", "order__quote__residence")
    .prefetch_related(
      Prefetch(
        "order__reservations",
        queryset=(
          MachineReservation.objects
          .filter(status="reserved")
          .select_related("machine__laundry_room")
          .order_by("machine__machine_type", "machine__code")
        ),
        to_attr="reserved_pair",
      )
    )
    .order_by("order__quote__service_date", "order__quote__window_start", "pk")
  )
  assignments = assignments.prefetch_related(
    Prefetch(
      "sessions",
      queryset=MachineSession.objects.filter(machine__machine_type="washer")
      .select_related("machine").order_by("started_at"),
      to_attr="wash_sessions",
    ),
    Prefetch(
      "sessions",
      queryset=MachineSession.objects.filter(machine__machine_type="dryer")
      .select_related("machine").order_by("started_at"),
      to_attr="dry_sessions",
    ),
  )
  return render(
    request,
    "workerpage/my_tasks.html",
    {"assignments": assignments},
  )


@login_required(login_url="accounts:worker_login")
@require_POST
def task_progress(request, assignment_id):
  if request.user.role != "worker":
    return HttpResponseForbidden("This page is for laundry workers only.")
  try:
    feedback = update_task(request.user.pk, assignment_id, request.POST.get("action"))
  except ValidationError as error:
    messages.error(request, " ".join(error.messages))
  except IntegrityError:
    messages.error(request, "The task or machine changed. Please refresh and try again.")
  except OperationalError as error:
    if connection.vendor != "sqlite" or "locked" not in str(error).lower():
      raise
    messages.error(request, "Another update is in progress. Please try again.")
  else:
    messages.success(request, feedback)
  return redirect("workerpage:my_tasks")


@login_required(login_url="accounts:worker_login")
@require_POST
def accept_task(request, order_id):
  if request.user.role != "worker":
    return HttpResponseForbidden(
      "This page is for laundry workers only."
    )

  try:
    assignment = accept_order(request.user.pk, order_id)
  except ValidationError as error:
    messages.error(request, " ".join(error.messages))
  except IntegrityError:
    messages.error(
      request,
      "The task or machine availability changed. Please try again.",
    )
  except OperationalError as error: # in case 2 ppl accept the same order at the same time, prevents database crash
    if connection.vendor != "sqlite" or "locked" not in str(error).lower():
      raise
    messages.error(
      request,
      "Another update is in progress. Please try again.",
    )
  else:
    messages.success(
      request,
      f"Order #{assignment.order_id} accepted. "
      f"Agreed payout: S${assignment.agreed_payout:.2f}.",
    )

  return redirect("workerpage:task_board")
