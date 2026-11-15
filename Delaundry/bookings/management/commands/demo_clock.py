import json
import os
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from bookings import clock


class Command(BaseCommand):
  help = "Set, advance or show the frozen clock for the current local demo session."
  # Clock setup must work before migrate creates the demo database.
  requires_system_checks = []

  def add_arguments(self, parser):
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("show")
    set_parser = actions.add_parser("set")
    set_parser.add_argument("time", help='Singapore time, e.g. "2026-11-16 09:45".')
    advance_parser = actions.add_parser("advance")
    advance_parser.add_argument("--minutes", type=int, required=True)

  def handle(self, *args, **options):
    try:
      root = clock.require_demo()
      if options["action"] == "show":
        value = clock.read_demo_time()
      else:
        value = self.change_clock(root, options)
    except (ImproperlyConfigured, ValueError, OverflowError, OSError) as error:
      raise CommandError(str(error)) from error
    self.stdout.write(self.style.SUCCESS(
      f"Demo session {settings.DEMO_SESSION}: {timezone.localtime(value):%d %b %Y, %H:%M:%S %Z} (frozen)"
    ))
    self.stdout.write(f"Database: {settings.DATABASES['default']['NAME']}")

  def change_clock(self, root, options):
    lock = root / "clock.lock"
    try:
      lock_file = lock.open("x")
    except FileExistsError as error:
      raise CommandError("Another clock command is running. Retry when it finishes.") from error
    temporary = root / "clock.tmp"
    try:
      with lock_file:
        current = clock.read_demo_time() if (root / "clock.json").exists() else None
        if options["action"] == "set":
          value = datetime.fromisoformat(options["time"])
          if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_default_timezone())
          if current is not None and value < current:
            raise CommandError("The demo clock cannot go backwards. Use a new demo session for another take.")
          # A missing clock must never reset timestamps in an existing demo database.
          database = root / "db.sqlite3"
          if current is None and database.exists() and database.stat().st_size:
            raise CommandError("This session already has a database but no clock. Use a new demo session.")
        else:
          if current is None:
            raise CommandError("Set the demo clock before advancing it.")
          if options["minutes"] <= 0:
            raise CommandError("Advance by a positive number of minutes.")
          value = current + timedelta(minutes=options["minutes"])
        # Readers see either the old or new complete timestamp, never partial JSON.
        temporary.write_text(json.dumps({"now": value.isoformat()}), encoding="utf-8")
        os.replace(temporary, root / "clock.json")
        return value
    finally:
      temporary.unlink(missing_ok=True)
      lock.unlink(missing_ok=True)
