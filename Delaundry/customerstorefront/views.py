from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.models import CustomerProfile
from bookings.availability import get_available_windows
from bookings.models import PriceQuote
from bookings.pricing import price_window, save_quote
from .forms import AvailabilityForm


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def availability(request):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")

  profile = CustomerProfile.objects.select_related("residence").filter(user=request.user).first()
  if profile is None:
    return HttpResponseForbidden("Your customer profile is missing. Please contact staff.")

  data = request.POST if request.method == "POST" else request.GET
  form = AvailabilityForm(data if data else {"date": timezone.localdate().isoformat()})
  if request.method == "POST":
    form.fields["window_start"].required = True
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

    if request.method == "POST" and selected_window is not None:
      try:
        # Recalculate on the server; the browser cannot supply its own price.
        price = price_window(profile.residence, selected_window)
        quote = save_quote(profile, selected_window, price)
      except ValueError:
        form.add_error("window_start", "This pickup window has started. Please choose another time.")
      else:
        return redirect("customerstorefront:quote_detail", quote_id=quote.pk)

    # Time may have advanced since availability was fetched (or a POST was rejected).
    pricing_time = timezone.now()
    windows = [window for window in windows if window["service_start"] > pricing_time]
    if selected_window is not None and selected_window not in windows:
      selected_window = None
    for window in windows:
      window["price"] = price_window(profile.residence, window, now=pricing_time)

  context = {
    "profile": profile,
    "form": form,
    "windows": windows,
    "selected_window": selected_window,
  }
  return render(request, "customerstorefront/availability.html", context)


@login_required(login_url="accounts:login")
@require_GET
def quote_detail(request, quote_id):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")
  # Filtering by the logged-in customer prevents access to another person's quote.
  quote = get_object_or_404(PriceQuote.objects.select_related("residence"), pk=quote_id, customer=request.user)
  return render(request, "customerstorefront/quote_detail.html", {"quote": quote})
