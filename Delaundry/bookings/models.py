from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.db.models.functions import Round
from django.utils import timezone

from bookings import clock
from facilities.models import BLOCK_CHOICES
from .storage import proof_storage, proof_upload_path


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
  created_at = models.DateTimeField(default=clock.now)
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
    return clock.now() >= self.expires_at or clock.now() >= self.service_start

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
  created_at = models.DateTimeField(default=clock.now, db_index=True)
  # Historical cancelled orders may not have a recorded cancellation time.
  cancelled_at = models.DateTimeField(null=True, blank=True)
  status = models.CharField(
    max_length=14,
    choices=[
      ("requested", "Requested"),
      ("confirmed", "Confirmed"),
      ("picked_up", "Picked up"),
      ("washing", "Washing"),
      ("drying", "Drying"),
      ("out_for_return", "Out for return"),
      ("delivered", "Delivered"),
      ("cancelled", "Cancelled"),
    ],
    default="requested",
  )

  class Meta:
    constraints = [
      models.CheckConstraint(
        condition=models.Q(status__in=[
          "requested", "confirmed", "picked_up", "washing", "drying",
          "out_for_return", "delivered", "cancelled",
        ]),
        name="order_valid_status",
      ),
      models.CheckConstraint(
        condition=(models.Q(cancelled_at__isnull=True) | models.Q(
          status="cancelled", cancelled_at__gte=models.F("created_at"),
        )),
        name="order_valid_cancellation_time",
      ),
    ]


class SupportRequest(models.Model):
  order = models.ForeignKey(LaundryOrder, on_delete=models.PROTECT, related_name="support_requests")
  category = models.CharField(max_length=10, choices=[
    ("late", "Late laundry"), ("missing", "Missing laundry"),
    ("damaged", "Damaged laundry"), ("other", "Other problem"),
  ])
  description = models.TextField(max_length=2000)
  created_at = models.DateTimeField(default=clock.now)
  status = models.CharField(max_length=10, choices=[("open", "Open"), ("resolved", "Resolved")], default="open")

  class Meta:
    constraints = [
      models.CheckConstraint(condition=models.Q(category__in=["late", "missing", "damaged", "other"]), name="support_valid_category"),
      models.CheckConstraint(condition=models.Q(status__in=["open", "resolved"]), name="support_valid_status"),
      models.CheckConstraint(condition=~models.Q(description=""), name="support_has_description"),
    ]

  def __str__(self):
    return f"Report #{self.pk} for order #{self.order_id}"


class JobAssignment(models.Model):
  order = models.OneToOneField(LaundryOrder, on_delete=models.PROTECT, related_name="assignment")
  worker = models.ForeignKey("accounts.WorkerProfile", on_delete=models.PROTECT, related_name="assignments")
  agreed_payout = models.DecimalField(
    max_digits=5,
    decimal_places=2,
  )
  accepted_at = models.DateTimeField(default=clock.now)
  picked_up_at = models.DateTimeField(null=True, blank=True)
  out_for_return_at = models.DateTimeField(null=True, blank=True)
  # A timestamp marks completion without a second assignment status to maintain.
  completed_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    constraints = [
      models.CheckConstraint(
        condition=models.Q(agreed_payout__gte=0),
        name="assignment_nonnegative_payout",
      ),
      models.CheckConstraint(
        condition=(models.Q(completed_at__isnull=True) | models.Q(
          out_for_return_at__isnull=False, completed_at__gte=models.F("out_for_return_at"),
        )),
        name="assignment_completion_after_return",
      ),
    ]


class DeliveryProof(models.Model):
  # Each assignment already belongs to exactly one order.
  assignment = models.OneToOneField(JobAssignment, on_delete=models.PROTECT, related_name="delivery_proof")
  photo = models.ImageField(storage=proof_storage, upload_to=proof_upload_path)
  note = models.CharField(max_length=500, blank=True)
  uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
  uploaded_at = models.DateTimeField(default=clock.now)

  class Meta:
    constraints = [
      models.CheckConstraint(condition=~models.Q(photo=""), name="delivery_proof_has_photo"),
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
  started_at = models.DateTimeField(default=clock.now)
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
  created_at = models.DateTimeField(default=clock.now, editable=False)

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
