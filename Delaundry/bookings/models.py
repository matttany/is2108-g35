from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.db.models.functions import Round
from django.utils import timezone
from facilities.models import BLOCK_CHOICES


SERVICE_START_TIMES = [time(hour) for hour in range(8, 21, 2)]


class PriceQuote(models.Model):
  id = models.AutoField(primary_key=True)
  customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
  residence = models.ForeignKey("facilities.Residence", on_delete=models.PROTECT)
  # Blank is retained only for historical quotes made before block-based booking.
  block = models.CharField(max_length=1, choices=BLOCK_CHOICES, blank=True, default="")
  unit_number = models.CharField(max_length=8)
  service_date = models.DateField()
  window_start = models.TimeField(choices=[(start, start.strftime("%H:%M")) for start in SERVICE_START_TIMES])
  created_at = models.DateTimeField(default=timezone.now)
  expires_at = models.DateTimeField()

  # Store the prices shown to the customer; later model runs must not change them.
  machine_fee = models.DecimalField(max_digits=5, decimal_places=2)
  worker_fee = models.DecimalField(max_digits=5, decimal_places=2)
  platform_fee = models.DecimalField(max_digits=5, decimal_places=2)
  total = models.DecimalField(max_digits=5, decimal_places=2)
  multiplier = models.DecimalField(max_digits=7, decimal_places=6)
  predicted_requests = models.FloatField(null=True, blank=True)
  reference_capacity = models.PositiveIntegerField()
  feature_snapshot = models.JSONField(default=dict)
  used_fallback = models.BooleanField(default=False)
  fallback_reason = models.CharField(max_length=120, blank=True)

  @property
  def service_start(self):
    return timezone.make_aware(datetime.combine(self.service_date, self.window_start))

  @property
  def pickup_end(self):
    return self.service_start + timedelta(minutes=15)

  @property
  def delivery_by(self):
    return self.service_start + timedelta(hours=2)

  @property
  def is_expired(self):
    return timezone.now() >= self.expires_at or timezone.now() >= self.service_start

  class Meta:
    constraints = [
      models.CheckConstraint(condition=models.Q(block__in=["", *"ABCDEF"]), name="quote_valid_block"),
      models.CheckConstraint(condition=models.Q(window_start__in=SERVICE_START_TIMES), name="quote_valid_window"),
      models.CheckConstraint(condition=models.Q(reference_capacity__gte=1), name="quote_positive_capacity"),
      models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("created_at")), name="quote_valid_expiry"),
      models.CheckConstraint(condition=models.Q(multiplier__gte=0.85, multiplier__lte=1.25), name="quote_bounded_multiplier"),
      models.CheckConstraint(
        condition=models.Q(machine_fee=2, worker_fee__gte=0.85, worker_fee__lte=1.25,
                           platform_fee__gte=0.85, platform_fee__lte=1.25),
        name="quote_bounded_fees",
      ),
      models.CheckConstraint(
        # Round the SQL sum too: SQLite stores decimal values as floating-point numbers.
        condition=models.Q(total=Round(models.F("machine_fee") + models.F("worker_fee") + models.F("platform_fee"), 2)),
        name="quote_total_matches_fees",
      ),
    ]


class LaundryOrder(models.Model):
  id = models.AutoField(primary_key=True)
  # Each submitted request uses one saved quote; the same quote cannot create two orders.
  quote = models.OneToOneField(PriceQuote, on_delete=models.PROTECT)
  created_at = models.DateTimeField(default=timezone.now, db_index=True)
  status = models.CharField(
    max_length=10,
    choices=[("requested", "Requested"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
    default="requested",
  )

  class Meta:
    constraints = [
      models.CheckConstraint(
        condition=models.Q(status__in=["requested", "confirmed", "cancelled"]),
        name="order_valid_status",
      ),
    ]

class JobAssignment(models.Model):
  order = models.OneToOneField(LaundryOrder, on_delete=models.PROTECT, related_name="assignment")
  worker = models.ForeignKey("accounts.WorkerProfile", on_delete=models.PROTECT, related_name="assignments")
  agreed_payout = models.DecimalField(
    max_digits=5,
    decimal_places=2,
  )
  accepted_at = models.DateTimeField(default=timezone.now)

  class Meta:
    constraints = [
      models.CheckConstraint(
        condition=models.Q(agreed_payout__gte=0),
        name="assignment_nonnegative_payout",
      ),
    ]

class WindowAllocation(models.Model):
  assignment = models.OneToOneField(JobAssignment, on_delete=models.PROTECT,related_name="allocation")
  laundry_room = models.ForeignKey("facilities.LaundryRoom",on_delete=models.PROTECT,)
  service_date = models.DateField()
  window_start = models.TimeField(
    choices=[
      (start, start.strftime("%H:%M"))
      for start in SERVICE_START_TIMES
    ],
  )
  slot_number = models.PositiveIntegerField()
  is_active = models.BooleanField(default=True)

  class Meta:
    constraints = [
      models.CheckConstraint(
        condition=models.Q(slot_number__gte=1),
        name="allocation_positive_slot",
      ),
      models.CheckConstraint(
        condition=models.Q(window_start__in=SERVICE_START_TIMES),
        name="allocation_valid_window",
      ),
      models.UniqueConstraint(
        fields=[
          "laundry_room",
          "service_date",
          "window_start",
          "slot_number",
        ],
        condition=models.Q(is_active=True),
        name="unique_active_window_slot",
      ),
    ]

class MachineSession(models.Model):
  assignment = models.ForeignKey(JobAssignment,on_delete=models.PROTECT,related_name="sessions")
  machine = models.ForeignKey("facilities.Machine",on_delete=models.PROTECT,related_name="sessions",)
  started_at = models.DateTimeField(default=timezone.now)
  expected_end = models.DateTimeField()
  ended_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    constraints = [
      models.UniqueConstraint(
        fields=["machine"],
        condition=models.Q(ended_at__isnull=True),
        name="unique_running_machine_session",
      ),
      models.CheckConstraint(
        condition=models.Q(expected_end__gt=models.F("started_at")),
        name="session_expected_end_after_start",
      ),
      models.CheckConstraint(
        condition=(
          models.Q(ended_at__isnull=True)
          | models.Q(ended_at__gte=models.F("started_at"))
        ),
        name="session_end_after_start",
      ),
    ]

class MachineReservation(models.Model):
  id = models.AutoField(primary_key=True)
  order = models.ForeignKey(LaundryOrder,on_delete=models.PROTECT,related_name="reservations", null=True, blank=True)
  assignment = models.ForeignKey(JobAssignment, on_delete=models.PROTECT, related_name="reservations", null=True, blank=True)
  machine = models.ForeignKey('facilities.Machine', on_delete=models.PROTECT)
  service_date = models.DateField()
  window_start = models.TimeField(
    choices=[(start, start.strftime("%H:%M")) for start in SERVICE_START_TIMES],
  )
  status = models.CharField(
    max_length=10,
    choices=[("reserved", "Reserved"), ("released", "Released")],
    default="reserved",
  )
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    constraints = [
      # A machine serves one job per window; released reservations keep their history.
      models.UniqueConstraint(
        fields=["machine", "service_date", "window_start"],
        condition=models.Q(status="reserved"),
        name="unique_reserved_machine_window",
      ),
      models.CheckConstraint(
        condition=models.Q(window_start__in=SERVICE_START_TIMES),
        name="reservation_valid_window_start",
      ),
      models.CheckConstraint(
        condition=models.Q(status__in=["reserved", "released"]),
        name="reservation_valid_status",
      ),
    ]
