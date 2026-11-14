from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.models import CustomerProfile
from bookings.availability import get_available_windows
from .forms import AvailabilityForm


@login_required(login_url="accounts:login")
@require_GET
def availability(request):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")

  profile = CustomerProfile.objects.select_related("residence").filter(user=request.user).first()
  if profile is None:
    return HttpResponseForbidden("Your customer profile is missing. Please contact staff.")

  form = AvailabilityForm(request.GET if request.GET else {"date": timezone.localdate().isoformat()})
  windows = []
  selected_window = None
  if form.is_valid():
    # Use the customer's saved hall, not a hall supplied through the URL.
    windows = get_available_windows(profile.residence, form.cleaned_data["date"])
    selected_start = form.cleaned_data["window_start"]
    if selected_start is not None:
      for window in windows:
        if window["window_start"] == selected_start:
          selected_window = window
          break
      if selected_window is None:
        form.add_error("window_start", "This window is no longer available. Please choose another time.")

  context = {
    "profile": profile,
    "form": form,
    "windows": windows,
    "selected_window": selected_window,
  }
  return render(request, "customerstorefront/availability.html", context)
