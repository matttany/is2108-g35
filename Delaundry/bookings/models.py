from datetime import time

from django.db import models


SERVICE_START_TIMES = [time(hour) for hour in range(8, 21, 2)]


class MachineReservation(models.Model):
  id = models.AutoField(primary_key=True)
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
