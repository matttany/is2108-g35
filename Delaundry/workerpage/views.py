from django.shortcuts import render

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET

from accounts.models import WorkerProfile


from django.db.models import Q
from django.utils import timezone

from bookings.models import LaundryOrder
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
    .order_by("quote__service_date", "quote__window_start", "created_at")
  )

  return render(
    request,
    "workerpage/task_board.html",
    {"profile": profile,
     "orders": orders},
  )