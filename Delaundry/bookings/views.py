from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import DeliveryProof


@login_required(login_url="accounts:login")
@never_cache
@require_GET
def delivery_photo(request, proof_id):
  if not request.user.is_active:
    return HttpResponseForbidden("An active account is required.")
  proofs = DeliveryProof.objects.select_related("assignment")
  if not request.user.is_staff:
    # Check ownership on every image request, even when its URL is known.
    allowed = Q(pk__in=[])
    if request.user.role == "customer":
      allowed = Q(assignment__order__quote__customer=request.user)
    elif request.user.role == "worker":
      allowed = Q(assignment__worker__user=request.user)
    proofs = proofs.filter(allowed)
  proof = get_object_or_404(proofs, pk=proof_id)
  try:
    photo = proof.photo.open("rb")
  except FileNotFoundError as error:
    raise Http404("The delivery photo is unavailable.") from error
  extension = "png" if proof.photo.name.endswith(".png") else "jpg"
  response = FileResponse(
    photo, content_type="image/png" if extension == "png" else "image/jpeg",
    filename=f"delivery-{proof.assignment.order_id}.{extension}",
  )
  response["X-Content-Type-Options"] = "nosniff"
  return response
