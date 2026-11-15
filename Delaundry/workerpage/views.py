from decimal import Decimal

from django.shortcuts import get_object_or_404, render

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache

from accounts.models import WorkerProfile


from django.db.models import Count, Prefetch, Q, Sum
from bookings import clock

from bookings.models import DeliveryProof, JobAssignment, LaundryOrder, MachineReservation, MachineSession

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from bookings.acceptance import accept_order
from bookings.progress import update_task
from bookings.delivery import complete_delivery
from .forms import DeliveryProofForm
from .reminders import cycle_reminder, return_reminder
# Create your views here.


@login_required(login_url="accounts:worker_login")
@never_cache
@require_http_methods(["GET", "POST"])
def delivery_proof(request, assignment_id):
  profile = WorkerProfile.objects.filter(user=request.user).first()
  if (
    request.user.role != "worker" or not request.user.is_active
    or profile is None or profile.approval_status != "approved"
  ):
    return HttpResponseForbidden("An active, approved worker account is required.")
  assignment = get_object_or_404(
    JobAssignment.objects.select_related("order__quote__residence"),
    pk=assignment_id, worker=profile,
  )
  proof = DeliveryProof.objects.select_related("uploaded_by").filter(assignment=assignment).first()
  form = DeliveryProofForm(request.POST, request.FILES) if request.method == "POST" else DeliveryProofForm()
  # A completed submission is a receipt; revisiting it never replaces the photo.
  if request.method == "POST" and proof is not None:
    return redirect("workerpage:delivery_proof", assignment_id=assignment.pk)
  if request.method == "POST" and form.is_valid():
    try:
      complete_delivery(request.user.pk, assignment.pk, form.cleaned_data["photo"], form.cleaned_data["note"])
    except ValidationError as error:
      form.add_error(None, " ".join(error.messages))
    except IntegrityError:
      form.add_error(None, "This task changed. Refresh the page before trying again.")
    except OperationalError as error:
      if connection.vendor != "sqlite" or "locked" not in str(error).lower():
        raise
      form.add_error(None, "Another update is in progress. Please try again.")
    except OSError:
      form.add_error(None, "The photo could not be saved. Please try again.")
    else:
      messages.success(request, "Delivery recorded. Your task is completed.")
      return redirect("workerpage:delivery_proof", assignment_id=assignment.pk)
  return render(request, "workerpage/delivery_proof.html", {
    "assignment": assignment, "quote": assignment.order.quote, "proof": proof, "form": form,
  })

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

  now = clock.localtime()

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
def earnings(request):
  if request.user.role != "worker":
    return HttpResponseForbidden("This page is for laundry workers only.")

  profile = WorkerProfile.objects.filter(user=request.user).first()
  if profile is None:
    return HttpResponseForbidden("Your worker profile is missing.")

  completed_assignments = (
    JobAssignment.objects
    .filter(
      worker=profile,
      completed_at__isnull=False,
      order__status="delivered",
    )
    .order_by("-completed_at", "-pk")
  )
  summary = completed_assignments.aggregate(
    total=Sum("agreed_payout", default=Decimal("0.00")),
    count=Count("pk"),
  )
  return render(
    request,
    "workerpage/earnings.html",
    {
      "completed_assignments": completed_assignments,
      "total_earnings": summary["total"],
      "completed_count": summary["count"],
    },
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
  checked_at = clock.now()
  for assignment in assignments:
    assignment.return_reminder = return_reminder(
      assignment.order.quote.delivery_by, checked_at,
    )
    for session in assignment.wash_sessions + assignment.dry_sessions:
      session.reminder = cycle_reminder(session, checked_at)
  return render(
    request,
    "workerpage/my_tasks.html",
    {"assignments": assignments, "checked_at": checked_at},
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
