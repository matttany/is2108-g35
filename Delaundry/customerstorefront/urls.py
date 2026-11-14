from django.urls import path

from . import views

app_name = "customerstorefront"

urlpatterns = [
  path("availability/", views.availability, name="availability"),
]
