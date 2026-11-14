from django.urls import path

from . import views

app_name = "customerstorefront"

urlpatterns = [
  path("availability/", views.availability, name="availability"),
  path("quotes/<int:quote_id>/", views.quote_detail, name="quote_detail"),
]
