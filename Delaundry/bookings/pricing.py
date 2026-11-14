import logging
import math
import warnings
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache

from django.utils import timezone

from facilities.models import Machine
from ml.features import ML_DIR, calendar_features
from .models import LaundryOrder, MachineReservation, PriceQuote


logger = logging.getLogger(__name__)
MODEL_PATH = ML_DIR / "artifacts" / "demand_model.joblib"
QUOTE_MINUTES = 15


def get_live_features(residence, window, now):
  pickup = timezone.localtime(window["service_start"])
  return {
    "residence": residence.name,
    "block": window["block"],
    "weekday": pickup.weekday(),
    "pickup_hour": pickup.hour,
    "lead_hours": round((pickup - now).total_seconds() / 3600, 4),
    # Count submissions, including later cancellations; browsing quotes is not demand.
    "recent_requests": LaundryOrder.objects.filter(
      quote__residence=residence, quote__block=window["block"],
      created_at__gte=now - timedelta(hours=24), created_at__lte=now,
    ).count(),
    # Count washers only so a washer/dryer reservation pair represents one booking.
    "known_bookings": MachineReservation.objects.filter(
      machine__laundry_room__residence=residence, machine__machine_type="washer",
      machine__laundry_room__block=window["block"],
      service_date=pickup.date(), window_start=pickup.time(), status="reserved",
    ).count(),
    "operational_machines": Machine.objects.filter(
      laundry_room__residence=residence, laundry_room__is_active=True,
      laundry_room__block=window["block"],
      laundry_room__residence__is_active=True, status="ACTIVE",
    ).count(),
  }


@lru_cache(maxsize=1)
def load_model(path, modified_at):
  import joblib
  from sklearn.exceptions import InconsistentVersionWarning

  # Load only our local trained artifact. Incompatible versions use neutral pricing.
  with warnings.catch_warnings():
    warnings.simplefilter("error", InconsistentVersionWarning)
    return joblib.load(path)


def predict_demand(features):
  model = load_model(str(MODEL_PATH), MODEL_PATH.stat().st_mtime_ns)
  if "residence=" + features["residence"] not in model.named_steps["features"].vocabulary_:
    raise ValueError("This residence was not included in model training.")
  if "block=" + features["block"] not in model.named_steps["features"].vocabulary_:
    raise ValueError("This block was not included in model training.")
  prediction = float(model.predict([features])[0])
  if not math.isfinite(prediction) or prediction < 0:
    raise ValueError("Demand prediction must be finite and non-negative.")
  return prediction


def calculate_fees(predicted_requests, capacity):
  if capacity < 1:
    raise ValueError("A quote requires an available washer/dryer pair.")
  multiplier = Decimal("1.000000")
  if predicted_requests is not None:
    pressure = Decimal(str(predicted_requests)) / Decimal(capacity)
    multiplier = max(Decimal("0.85"), min(Decimal("1.25"), Decimal("1") + Decimal("0.15") * (pressure - 1)))
    multiplier = multiplier.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
  worker_fee = multiplier.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  platform_fee = multiplier.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  machine_fee = Decimal("2.00")
  return {
    "multiplier": multiplier, "machine_fee": machine_fee,
    "worker_fee": worker_fee, "platform_fee": platform_fee,
    "total": machine_fee + worker_fee + platform_fee,
  }


def price_window(residence, window, now=None):
  now = now or timezone.now()
  if window["service_start"] <= now:
    raise ValueError("This pickup window has already started.")
  features = get_live_features(residence, window, now)
  prediction = None
  fallback_reason = ""
  try:
    features.update(calendar_features(timezone.localtime(window["service_start"]).date()))
    prediction = predict_demand(features)
  except Exception as error:
    # Only ML/calendar failure falls back; database and availability errors remain visible.
    fallback_reason = type(error).__name__
    logger.warning("Demand forecast unavailable; using neutral pricing: %s", error)
  return {
    **calculate_fees(prediction, window["available_pairs"]),
    "predicted_requests": prediction,
    "reference_capacity": window["available_pairs"],
    "feature_snapshot": features,
    "used_fallback": bool(fallback_reason),
    "fallback_reason": fallback_reason,
  }


def save_quote(profile, window, price):
  now = timezone.now()
  if not profile.block or window["block"] != profile.block:
    raise ValueError("The quote must use the customer's saved block.")
  if window["service_start"] <= now:
    raise ValueError("This pickup window has already started.")
  return PriceQuote.objects.create(
    customer=profile.user, residence=profile.residence, block=profile.block, unit_number=profile.unitNum,
    service_date=timezone.localtime(window["service_start"]).date(),
    window_start=window["window_start"], created_at=now,
    expires_at=min(now + timedelta(minutes=QUOTE_MINUTES), window["service_start"]),
    **price,
  )
