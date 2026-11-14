from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import CustomerProfile, WorkerProfile
from bookings.models import LaundryOrder, MachineReservation, MachineSession, SERVICE_START_TIMES
from facilities.models import Machine, Residence


ACTIVE_ORDER_STATUSES = ["confirmed", "picked_up", "washing", "drying", "out_for_return"]


def dashboard_data(filters, now=None):
  now = now or timezone.localtime()
  orders = LaundryOrder.objects.all()
  customers = CustomerProfile.objects.filter(user__role="customer")
  workers = WorkerProfile.objects.filter(
    user__role="worker", user__is_active=True, approval_status="approved",
  )
  machines = Machine.objects.filter(
    status="ACTIVE", laundry_room__is_active=True,
    laundry_room__residence__is_active=True,
  )
  hall = filters["residence"]
  if hall:
    orders = orders.filter(quote__residence=hall)
    customers = customers.filter(residence=hall)
    workers = workers.filter(residence=hall)
    machines = machines.filter(laundry_room__residence=hall)
  if filters["status"]:
    orders = orders.filter(status=filters["status"])
  if filters["start_date"]:
    orders = orders.filter(created_at__date__gte=filters["start_date"])
  if filters["end_date"]:
    orders = orders.filter(created_at__date__lte=filters["end_date"])

  machines = machines.exclude(pk__in=MachineSession.objects.filter(
    ended_at__isnull=True,
  ).values("machine_id"))
  for start in SERVICE_START_TIMES:
    window = timezone.make_aware(datetime.combine(now.date(), start))
    if window <= now < window + timedelta(hours=2):
      machines = machines.exclude(pk__in=MachineReservation.objects.filter(
        service_date=now.date(), window_start=start, status="reserved",
      ).values("machine_id"))
      break

  counts = orders.aggregate(
    total=Count("pk"),
    pending=Count("pk", filter=Q(status="requested")),
    active=Count("pk", filter=Q(status__in=ACTIVE_ORDER_STATUSES)),
    completed=Count("pk", filter=Q(status="delivered", assignment__completed_at__isnull=False)),
  )
  hall_names = dict(Residence._meta.get_field("name").choices)
  halls = list(orders.values("quote__residence__name").annotate(
    count=Count("pk"),
  ).order_by("quote__residence__name"))
  for row in halls:
    code = row["quote__residence__name"]
    row["label"] = hall_names.get(code, code)
  status_names = dict(LaundryOrder._meta.get_field("status").choices)
  statuses = list(orders.values("status").annotate(count=Count("pk")).order_by("status"))
  for row in statuses:
    row["label"] = status_names.get(row["status"], row["status"])

  return {
    "checked_at": now,
    "order_total": counts["total"],
    "cards": [
      {"label": "Customers", "count": customers.count()},
      {"label": "Approved workers", "count": workers.count()},
      {"label": "Pending requests", "count": counts["pending"]},
      {"label": "Active orders", "count": counts["active"]},
      {"label": "Completed jobs", "count": counts["completed"]},
      {"label": "Machines available now", "count": machines.count()},
    ],
    "hall_summary": halls,
    "status_summary": statuses,
  }
