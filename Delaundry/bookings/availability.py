from datetime import datetime, timedelta

from django.utils import timezone

from facilities.models import LaundryRoom, Machine
from .models import MachineReservation, SERVICE_START_TIMES


BOOKING_DAYS_AHEAD = 7


def get_available_windows(residence, service_date):
  now = timezone.localtime()
  if not residence.is_active:
    return []
  if service_date < now.date() or service_date > now.date() + timedelta(days=BOOKING_DAYS_AHEAD):
    return []

  rooms = list(LaundryRoom.objects.filter(residence=residence, is_active=True).order_by("block"))
  machines = list(Machine.objects.filter(laundry_room__in=rooms, status="ACTIVE").order_by("code"))
  reservations = list(MachineReservation.objects.filter(
    machine__laundry_room__residence=residence,
    service_date=service_date,
    status="reserved",
  ).values_list("window_start", "machine_id"))

  windows = []
  for start in SERVICE_START_TIMES:
    service_start = timezone.make_aware(datetime.combine(service_date, start))
    if service_start <= now:
      continue # A customer cannot select a pickup window that has already started.

    reserved_ids = {machine_id for booked_start, machine_id in reservations if booked_start == start}
    available_rooms = []
    available_pairs = 0

    for room in rooms:
      washer_ids = []
      dryer_ids = []
      for machine in machines:
        if machine.laundry_room_id != room.pk or machine.pk in reserved_ids:
          continue
        if machine.machine_type == "washer":
          washer_ids.append(machine.pk)
        elif machine.machine_type == "dryer":
          dryer_ids.append(machine.pk)

      # Each job needs a washer AND dryer in the same room.
      pair_count = min(len(washer_ids), len(dryer_ids))
      if pair_count > 0:
        available_pairs += pair_count
        available_rooms.append({
          "room": room,
          "washer_ids": washer_ids,
          "dryer_ids": dryer_ids,
          "available_pairs": pair_count,
        })

    if available_pairs > 0:
      windows.append({
        "window_start": start,
        "service_start": service_start,
        "pickup_end": service_start + timedelta(minutes=15),
        "delivery_by": service_start + timedelta(hours=2),
        "available_pairs": available_pairs,
        "rooms": available_rooms,
      })

  return windows
