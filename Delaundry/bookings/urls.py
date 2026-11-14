from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
  path("delivery-proofs/<int:proof_id>/photo/", views.delivery_photo, name="delivery_photo"),
]
