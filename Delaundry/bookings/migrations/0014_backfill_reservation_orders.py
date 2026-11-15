from django.db import migrations, models
import django.db.models.deletion


def backfill_reservation_orders(apps, schema_editor):
  MachineReservation = apps.get_model("bookings", "MachineReservation")
  # Use the database being migrated, including when --database is supplied.
  reservations = MachineReservation.objects.using(schema_editor.connection.alias)
  conflicting = reservations.filter(
    order__isnull=False, assignment__isnull=False,
  ).exclude(order_id=models.F("assignment__order_id"))
  if conflicting.exists():
    raise RuntimeError(
      "Cannot remove reservation assignments: some reservations link to different "
      "orders through order and assignment. Correct those links, then run migrate again."
    )
  if reservations.filter(order__isnull=True, assignment__isnull=True).exists():
    raise RuntimeError(
      "Cannot require reservation orders: some reservations have neither an order "
      "nor an assignment. Identify their correct orders before running migrate again."
    )

  missing_orders = (
    reservations
    .filter(order__isnull=True, assignment__isnull=False)
    .select_related("assignment")
  )
  for reservation in missing_orders.iterator():
    reservation.order_id = reservation.assignment.order_id
    reservation.save(using=schema_editor.connection.alias, update_fields=["order"])


class Migration(migrations.Migration):

  dependencies = [
    ("bookings", "0013_remove_window_allocation"),
  ]

  operations = [
    migrations.RunPython(
      backfill_reservation_orders,
      # Reversing keeps recovered order links; removed assignment values cannot be restored.
      migrations.RunPython.noop,
    ),
    migrations.AlterField(
      model_name="machinereservation",
      name="order",
      field=models.ForeignKey(
        on_delete=django.db.models.deletion.PROTECT,
        related_name="reservations",
        to="bookings.laundryorder",
      ),
    ),
    migrations.RemoveField(
      model_name="machinereservation",
      name="assignment",
    ),
  ]
