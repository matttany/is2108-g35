from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, connection, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.models import CustomerProfile
from bookings.availability import get_available_windows
from bookings.models import DeliveryProof, JobAssignment, LaundryOrder, MachineReservation, PriceQuote
from bookings.pricing import price_window, save_quote
from .forms import AvailabilityForm
from .tracking import get_order_timeline


@login_required(login_url="accounts:login")
@require_GET
def order_list(request):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")
  # Include previous orders even if the customer has since changed their address.
  orders = LaundryOrder.objects.filter(quote__customer=request.user).select_related(
    "quote__residence",
  ).order_by("-created_at", "-pk")
  page = Paginator(orders, 10).get_page(request.GET.get("page"))
  return render(request, "customerstorefront/order_list.html", {"page": page})


@login_required(login_url="accounts:login")
@never_cache
@require_GET
def order_detail(request, order_id):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")
  order = get_object_or_404(
    LaundryOrder.objects.select_related("quote__residence"),
    pk=order_id, quote__customer=request.user,
  )
  assignment = JobAssignment.objects.select_related("worker__user").filter(order=order).first()
  sessions = []
  proof = None
  if assignment is not None:
    sessions = list(assignment.sessions.select_related("machine__laundry_room").order_by("started_at", "pk"))
    # Only load proof belonging to the customer's already-authorised order.
    proof = DeliveryProof.objects.select_related("uploaded_by").filter(assignment=assignment).first()
  context = {
    "order": order, "quote": order.quote, "assignment": assignment, "sessions": sessions,
    "proof": proof,
    "timeline": get_order_timeline(order, assignment, sessions),
  }
  return render(request, "customerstorefront/order_detail.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def availability(request):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")

  profile = CustomerProfile.objects.select_related("residence").filter(user=request.user).first()
  if profile is None:
    return HttpResponseForbidden("Your customer profile is missing. Please contact staff.")
  if not profile.block:
    return redirect("accounts:customer_block")

  data = request.POST if request.method == "POST" else request.GET
  form = AvailabilityForm(data if data else {"date": timezone.localdate().isoformat()})
  if request.method == "POST":
    form.fields["window_start"].required = True
  windows = []
  selected_window = None
  if form.is_valid():
    # Both hall and block come from the customer's profile, not the browser.
    windows = get_available_windows(profile.residence, form.cleaned_data["date"], profile.block)
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
  # Quote expiry only limits submission; it does not cancel an existing order.
  order = LaundryOrder.objects.filter(quote=quote).first()
  return render(request, "customerstorefront/quote_detail.html", {"quote": quote, "order": order})


@login_required(login_url="accounts:login")
@require_POST
def submit_request(request, quote_id):
  if not request.user.is_active or request.user.role != "customer":
    return HttpResponseForbidden("This page is for customers only.")

  try:
    with transaction.atomic():
      quote = get_object_or_404(
        PriceQuote.objects.select_for_update().select_related("residence"),
        pk=quote_id, customer=request.user,
      )
      # A double-click or retry shows the existing order, even if its quote has since expired.
      if LaundryOrder.objects.filter(quote=quote).exists():
        return redirect("customerstorefront:quote_detail", quote_id=quote.pk)

      profile = CustomerProfile.objects.select_for_update().select_related("residence").filter(user=request.user).first()
      if profile is None:
        raise ValidationError("Your customer profile is missing. Please contact staff.")
      if not quote.block or (
        profile.residence != quote.residence
        or profile.block != quote.block
        or profile.unitNum != quote.unit_number
      ):
        raise ValidationError("Your pickup address has changed or is incomplete. Please get a new quote.")
      if quote.is_expired:
        raise ValidationError("This quote has expired. Please choose a pickup time and get a new quote.")

      windows = get_available_windows(quote.residence, quote.service_date, quote.block)
      selected_window = next((window for window in windows if window["window_start"] == quote.window_start), None)
      if selected_window is None:
        raise ValidationError("This pickup window is no longer available. Please choose another time.")
      if quote.is_expired:
        raise ValidationError("This quote expired while availability was being checked. Please get a new quote.")

      # Reuse the stored quote and its total; submission never recalculates prices.
      order = LaundryOrder.objects.create(quote=quote, status="requested")
      room = selected_window["rooms"][0]
      # Reserve a same-room pair for the entire two-hour window, before worker acceptance.
      for machine_id in [room["washer_ids"][0], room["dryer_ids"][0]]:
        MachineReservation.objects.create(
          order=order, machine_id=machine_id,
          service_date=quote.service_date, window_start=quote.window_start,
          status="reserved",
        )
  except ValidationError as error:
    messages.error(request, " ".join(error.messages))
  except IntegrityError:
    # Atomic rollback removes the order and first reservation if the pair cannot be saved.
    # A competing submission of this same quote may already have completed successfully.
    if not LaundryOrder.objects.filter(quote_id=quote_id, quote__customer=request.user).exists():
      messages.error(request, "The machines could not be reserved. Please check availability and try again.")
  except OperationalError as error:
    # SQLite cannot lock individual rows; a competing write may need a retry.
    if connection.vendor != "sqlite" or "locked" not in str(error).lower():
      raise
    messages.error(request, "Another update is in progress. Please try submitting your request again.")

  return redirect("customerstorefront:quote_detail", quote_id=quote_id)
