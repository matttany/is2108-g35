from django.urls import path

from . import views

app_name = "customerstorefront"

urlpatterns = [
  path("availability/", views.availability, name="availability"),
  path("quotes/<int:quote_id>/", views.quote_detail, name="quote_detail"),
  path("quotes/<int:quote_id>/submit/", views.submit_request, name="submit_request"),
]
