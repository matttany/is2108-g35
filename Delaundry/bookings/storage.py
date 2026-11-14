from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateProofStorage(FileSystemStorage):
  def url(self, name):
    # Proof photos are served by an authorised view, never a public media URL.
    raise ValueError("Use the protected delivery photo view.")


def proof_storage():
  return PrivateProofStorage(location=settings.PRIVATE_PROOF_ROOT)


def proof_upload_path(instance, filename):
  extension = filename.rsplit(".", 1)[-1]
  return f"delivery/{uuid4().hex}.{extension}"
