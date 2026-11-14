import csv
from datetime import date
from functools import lru_cache
from pathlib import Path


ML_DIR = Path(__file__).resolve().parent
FEATURE_COLUMNS = [
  "residence", "weekday", "pickup_hour", "is_term_time", "is_public_holiday",
  "lead_hours", "recent_requests", "known_bookings", "operational_machines",
]


def read_feature_row(row):
  # CSV values are strings; use the same numeric types as live feature queries.
  return {name: row[name] if name == "residence" else float(row[name]) for name in FEATURE_COLUMNS}


@lru_cache(maxsize=1)
def load_calendar():
  with (ML_DIR / "data" / "academic_calendar.csv").open(encoding="utf-8", newline="") as file:
    periods = list(csv.DictReader(file))
  with (ML_DIR / "data" / "public_holidays.csv").open(encoding="utf-8", newline="") as file:
    holidays = {row["date"] for row in csv.DictReader(file)}
  return periods, holidays


def calendar_features(service_date):
  periods, holidays = load_calendar()
  for period in periods:
    if date.fromisoformat(period["start_date"]) <= service_date <= date.fromisoformat(period["end_date"]):
      return {
        "is_term_time": int(period["is_term_time"]),
        "is_public_holiday": int(service_date.isoformat() in holidays),
      }
  # An uncovered date is unknown, rather than silently treated as a vacation.
  raise ValueError("The pickup date is outside the supported calendar.")
