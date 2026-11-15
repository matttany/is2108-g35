import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


def require_demo():
  if not getattr(settings, "DEMO_MODE", False) or not settings.DEBUG:
    raise ImproperlyConfigured("Enable DELAUNDRY_DEMO=1 with DEBUG=True for the local demo clock.")
  root = Path(settings.DEMO_ROOT).resolve()
  database = settings.DATABASES["default"]
  # Refuse accidental overrides that would run simulated time against regular data.
  if (
    root.parent != (settings.BASE_DIR / "demo_data").resolve()
    or database["ENGINE"] != "django.db.backends.sqlite3"
    or Path(database["NAME"]).resolve() != root / "db.sqlite3"
    or Path(settings.PRIVATE_PROOF_ROOT).resolve() != root / "uploads"
  ):
    raise ImproperlyConfigured("Demo mode requires its separate demo database and uploads.")
  return root


def read_demo_time():
  path = require_demo() / "clock.json"
  try:
    value = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["now"])
    if timezone.is_naive(value):
      raise ValueError("The saved clock must include its timezone.")
    return value
  except FileNotFoundError as error:
    raise ImproperlyConfigured('Set the demo clock first: python manage.py demo_clock set "2026-11-16 09:45"') from error
  except (OSError, ValueError, KeyError, TypeError) as error:
    raise ImproperlyConfigured("The demo clock file is unreadable or invalid. Use a new demo session.") from error


def now():
  if getattr(settings, "DEMO_MODE", False):
    return read_demo_time()
  return timezone.now()


def localtime(value=None):
  return timezone.localtime(now() if value is None else value)


def localdate():
  return localtime().date()
