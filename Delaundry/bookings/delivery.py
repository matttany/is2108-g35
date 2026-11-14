from datetime import timedelta
from io import BytesIO
import logging
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import User, WorkerProfile
from facilities.models import Machine
from .models import DeliveryProof, JobAssignment, LaundryOrder


logger = logging.getLogger(__name__)
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 12_000_000


def prepare_delivery_photo(photo):
  if photo is None or not getattr(photo, "size", 0):
    raise ValidationError("Choose a delivery photo.")
  if photo.size > MAX_PHOTO_BYTES:
    raise ValidationError("The photo must be 5 MB or smaller.")
  try:
    photo.seek(0)
    with warnings.catch_warnings():
      warnings.simplefilter("error", Image.DecompressionBombWarning)
      with Image.open(photo) as picture:
        image_format = picture.format
        if image_format not in ["JPEG", "PNG"]:
          raise ValidationError("Choose a JPEG or PNG photo.")
        if picture.width * picture.height > MAX_PHOTO_PIXELS:
          raise ValidationError("The photo must be 12 megapixels or smaller.")
        picture.verify()
      photo.seek(0)
      with Image.open(photo) as picture:
        picture.load()
        picture = ImageOps.exif_transpose(picture).convert("RGB")
        # Re-encode pixels to remove metadata and any appended non-image content.
        clean_picture = Image.new("RGB", picture.size)
        clean_picture.paste(picture)
        output = BytesIO()
        clean_picture.save(output, format=image_format)
  except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
          Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
    raise ValidationError("The photo could not be read. Choose a valid JPEG or PNG.") from error
  finally:
    photo.seek(0)
  if output.tell() > MAX_PHOTO_BYTES:
    raise ValidationError("The processed photo is too large. Choose a smaller photo.")
  extension = "jpg" if image_format == "JPEG" else "png"
  return ContentFile(output.getvalue(), name=f"proof.{extension}")


def check_delivery_stages(assignment, order, now):
  if order.status != "out_for_return" or assignment.completed_at is not None:
    raise ValidationError("This task must be ready for return before recording delivery.")
  sessions = list(assignment.sessions.select_for_update().select_related("machine__laundry_room"))
  washes = [session for session in sessions if session.machine.machine_type == "washer"]
  dries = [session for session in sessions if session.machine.machine_type == "dryer"]
  if len(sessions) != 2 or len(washes) != 1 or len(dries) != 1:
    raise ValidationError("Exactly one completed wash and dry cycle is required.")
  wash, dry = washes[0], dries[0]
  if wash.ended_at is None or dry.ended_at is None:
    raise ValidationError("Finish both machine cycles before recording delivery.")
  if assignment.picked_up_at is None or assignment.out_for_return_at is None:
    raise ValidationError("Collection and return preparation must be recorded first.")
  if not (
    assignment.accepted_at <= assignment.picked_up_at <= wash.started_at
    and wash.ended_at <= dry.started_at
    and dry.ended_at <= assignment.out_for_return_at <= now
  ):
    raise ValidationError("The recorded stages are not in the correct time order.")
  quote = order.quote
  if not quote.service_start <= assignment.picked_up_at <= quote.pickup_end:
    raise ValidationError("Collection must be recorded within the pickup window.")
  for session, minutes in [(wash, Machine.WASH_CYCLE_MINUTES), (dry, Machine.DRY_CYCLE_MINUTES)]:
    if (
      session.expected_end != session.started_at + timedelta(minutes=minutes)
      or session.ended_at < session.expected_end
      or session.expected_end > quote.delivery_by
    ):
      raise ValidationError("Both 30-minute cycles must be completed in the service window.")

  reservations = list(order.reservations.select_for_update().select_related("machine__laundry_room"))
  if len(reservations) != 2 or {row.machine_id for row in reservations} != {wash.machine_id, dry.machine_id}:
    raise ValidationError("The completed cycles must use this order's reserved machine pair.")
  if wash.machine.laundry_room_id != dry.machine.laundry_room_id:
    raise ValidationError("The washer and dryer must be in the same room.")
  for reservation in reservations:
    room = reservation.machine.laundry_room
    if (
      reservation.status != "reserved"
      or reservation.service_date != quote.service_date
      or reservation.window_start != quote.window_start
      or room.residence_id != quote.residence_id
      or room.block != quote.block
    ):
      raise ValidationError("The reserved machines do not match this order's location and window.")


def complete_delivery(user_id, assignment_id, photo, note=""):
  saved_name = None
  storage = DeliveryProof._meta.get_field("photo").storage
  try:
    # Own the outer transaction so a failed commit can also clean up the new file.
    with transaction.atomic(durable=True):
      user = User.objects.select_for_update().get(pk=user_id)
      profile = WorkerProfile.objects.select_for_update().filter(user=user).first()
      if profile is None or user.role != "worker" or not user.is_active or profile.approval_status != "approved":
        raise ValidationError("An active, approved worker account is required.")
      assignment = get_object_or_404(JobAssignment.objects.select_for_update(), pk=assignment_id, worker=profile)
      order = LaundryOrder.objects.select_for_update().get(pk=assignment.order_id)
      existing = DeliveryProof.objects.filter(assignment=assignment).first()
      if existing is not None:
        if order.status == "delivered" and assignment.completed_at is not None:
          return existing
        raise ValidationError("This task has inconsistent delivery records. Please contact staff.")

      now = timezone.now()
      check_delivery_stages(assignment, order, now)
      clean_photo = prepare_delivery_photo(photo)
      note = note.strip()
      if len(note) > 500:
        raise ValidationError("The delivery note must be 500 characters or fewer.")
      changed = LaundryOrder.objects.filter(pk=order.pk, status="out_for_return").update(status="delivered")
      if changed != 1:
        raise ValidationError("This task changed. Please refresh and try again.")
      assignment.completed_at = now
      assignment.save(update_fields=["completed_at"])
      proof = DeliveryProof(assignment=assignment, uploaded_by=user, uploaded_at=now, note=note)
      proof.photo.save(clean_photo.name, clean_photo, save=False)
      saved_name = proof.photo.name
      proof.full_clean()
      proof.save()
    return proof
  except Exception:
    # Database rollback does not automatically remove a file already written.
    if saved_name is not None:
      try:
        storage.delete(saved_name)
      except OSError:
        logger.exception("Could not remove a delivery photo after rollback: %s", saved_name)
    raise
