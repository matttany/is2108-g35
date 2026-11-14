from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomerProfile, User
from bookings.availability import get_available_windows
from bookings.models import LaundryOrder
from bookings.pricing import price_window, save_quote
from facilities.models import Residence


DEMO_PASSWORD = "peepeepoopoo"


class Command(BaseCommand):
  help = "Create three demo customers and requested orders without reserving machines."

  def add_arguments(self, parser):
    parser.add_argument("--residence", default="temasek", help="Hall code, e.g. temasek or eusoff.")

  def handle(self, *args, **options):
    residence = Residence.objects.filter(name=options["residence"], is_active=True).first()
    if residence is None:
      raise CommandError("Choose an existing active residence.")
    service_date = timezone.localdate() + timedelta(days=1)
    messages = []

    # Roll back the entire seed if a block is unavailable or a demo identity conflicts.
    with transaction.atomic():
      for number, block in enumerate(["A", "A", "B"], start=1):
        username = f"demo_block_{number}"
        email = f"{username}@u.nus.edu"
        name = f"Demo Customer {number}"
        user = User.objects.filter(username=username).first()
        if user is not None:
          if user.email != email or user.name != name or user.role != "customer":
            raise CommandError(f"{username} is already used by a different account; nothing was changed.")
          profile = CustomerProfile.objects.filter(user=user).first()
          if profile is None or profile.residence != residence or profile.block != block:
            raise CommandError(f"{username} has a different profile; nothing was changed.")
          # Apply the shared demo password to accounts created by earlier seed runs too.
          if not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
          existing = LaundryOrder.objects.filter(quote__customer=user).select_related("quote").first()
          if existing is not None:
            messages.append(f"Kept order {existing.pk} for {username}: {existing.quote.service_date}, block {existing.quote.block}.")
            continue
        else:
          if User.objects.filter(email=email).exists():
            raise CommandError(f"The demo email {email} is already in use; nothing was changed.")
          # create_user stores a password hash, not the plain-text demo password.
          user = User.objects.create_user(username=username, email=email, name=name, role="customer", password=DEMO_PASSWORD)
          profile = CustomerProfile.objects.create(
            user=user, residence=residence, block=block, unitNum=f"#01-0{number}",
          )

        windows = get_available_windows(residence, service_date, block)
        if not windows:
          raise CommandError(f"No available window tomorrow in {residence}, block {block}; nothing was changed.")
        window = windows[(number - 1) % len(windows)]
        quote = save_quote(profile, window, price_window(residence, window))
        order = LaundryOrder.objects.create(quote=quote, status="requested")
        messages.append(
          f"Created order {order.pk} for {username}: {service_date}, block {block}, "
          f"pickup {window['window_start']:%H:%M}, total ${quote.total:.2f}."
        )

    for message in messages:
      self.stdout.write(self.style.SUCCESS(message))
    self.stdout.write("Demo orders are requests only; no machines have been reserved.")
