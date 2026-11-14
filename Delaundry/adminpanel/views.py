from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import WorkerProfile
from .forms import StaffLoginForm, WorkerApprovalForm, WorkerFilterForm


def staff_login(request):
  if request.user.is_authenticated and request.user.is_active and request.user.is_staff:
    return redirect("adminpanel:worker_list")

  if request.method == "POST":
    form = StaffLoginForm(request=request, data=request.POST)
    if form.is_valid():
      login(request, form.get_user())
      return redirect("adminpanel:worker_list")
  else:
    form = StaffLoginForm(request=request)

  return render(request, "adminpanel/login.html", {"form": form})


@require_POST
def staff_logout(request):
  logout(request)
  return redirect("adminpanel:login")


@login_required(login_url="adminpanel:login")
def worker_list(request):
  if not request.user.is_active or not request.user.is_staff:
    return HttpResponseForbidden("This page is for active staff accounts only.")

  form = WorkerFilterForm(request.GET)
  # Load the user and residence with each profile to avoid repeated queries.
  workers = WorkerProfile.objects.select_related("user", "residence").filter(user__role="worker")

  if form.is_valid():
    search = form.cleaned_data["search"]
    residence = form.cleaned_data["residence"]
    approval_status = form.cleaned_data["approval_status"]

    if search:
      # Q joins the two search conditions with OR.
      workers = workers.filter(Q(user__name__icontains=search) | Q(user__email__icontains=search))
    if residence:
      workers = workers.filter(residence=residence)
    if approval_status:
      workers = workers.filter(approval_status=approval_status)
  else:
    workers = workers.none()

  workers = workers.order_by("-user__date_joined", "pk")
  return render(request, "adminpanel/worker_list.html", {"form": form, "workers": workers})


@login_required(login_url="adminpanel:login")
def worker_review(request, worker_id):
  if not request.user.is_active or not request.user.is_staff:
    return HttpResponseForbidden("This page is for active staff accounts only.")

  worker = get_object_or_404(
    WorkerProfile.objects.select_related("user", "residence"),
    pk=worker_id,
    user__role="worker",
  )

  if request.method == "POST":
    form = WorkerApprovalForm(request.POST)
    if form.is_valid():
      status = form.cleaned_data["approval_status"]
      if status == "approved" and not worker.user.is_active:
        form.add_error("approval_status", "An inactive account cannot be approved.")
      else:
        # Keep the account and history; suspension only blocks eligibility for new work.
        worker.approval_status = status
        worker.save(update_fields=["approval_status"])
        messages.success(request, f"{worker.user.name}'s status is now {worker.get_approval_status_display()}.")
        return redirect("adminpanel:worker_review", worker_id=worker.pk)
  else:
    form = WorkerApprovalForm()

  return render(request, "adminpanel/worker_review.html", {"form": form, "worker": worker})
