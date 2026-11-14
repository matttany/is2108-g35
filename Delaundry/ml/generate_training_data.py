"""Run from Delaundry: python -m ml.generate_training_data"""
import csv
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from .features import FEATURE_COLUMNS, ML_DIR, calendar_features


def generate_data():
  rng = np.random.default_rng(42)
  halls = ["eusoff", "kentridge", "kingedward", "raffles", "sheares", "temasek"]
  rows = []
  service_date = date(2026, 1, 1)
  while service_date <= date(2026, 10, 31):
    calendar = calendar_features(service_date)
    for hall_index, hall in enumerate(halls):
      for hour in range(8, 21, 2):
        pickup = datetime.combine(service_date, time(hour), tzinfo=ZoneInfo("Asia/Singapore"))
        lead_hours = round(float(rng.uniform(0.25, 168)), 2)
        forecast_at = pickup - timedelta(hours=lead_hours)
        # Sample one block for each hall/window; demand and machines belong to that block.
        block_index = int(rng.integers(0, 6))
        block = "ABCDEF"[block_index]
        machines = int(rng.integers(2, 21))
        recent = int(rng.integers(0, 41))
        known = int(rng.integers(0, machines // 2 + 1))
        features = {
          "residence": hall,
          "block": block,
          "weekday": service_date.weekday(),
          "pickup_hour": hour,
          **calendar,
          "lead_hours": lead_hours,
          "recent_requests": recent,
          "known_bookings": known,
          "operational_machines": machines,
        }
        # These are assumed demand patterns, not measurements of NUS residents.
        daily_demand = (
          0.5 + hall_index * 0.08 + block_index * 0.04 + 0.5 * calendar["is_term_time"]
          + 0.4 * (service_date.weekday() >= 5) + 0.6 * (hour >= 18)
          + 0.2 * calendar["is_public_holiday"] + 0.04 * recent
          + 0.06 * known + 0.02 * machines
        )
        # Target: NEW requests after forecast_at and before pickup, excluding known bookings.
        expected_new = daily_demand * lead_hours / 24
        new_requests = int(rng.poisson(expected_new))
        rows.append({
          "forecast_at": forecast_at.isoformat(), "pickup_at": pickup.isoformat(),
          **features, "new_requests": new_requests, "is_synthetic": 1,
        })
    service_date += timedelta(days=1)

  rows.sort(key=lambda row: row["forecast_at"])
  path = ML_DIR / "data" / "synthetic_demand.csv"
  with path.open("w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=["forecast_at", "pickup_at", *FEATURE_COLUMNS, "new_requests", "is_synthetic"])
    writer.writeheader()
    writer.writerows(rows)
  print(f"Wrote {len(rows)} synthetic forecasts to {path}")


if __name__ == "__main__":
  generate_data()
