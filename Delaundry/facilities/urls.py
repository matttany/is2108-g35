from django.urls import path
from . import views

app_name = "facilities"

urlpatterns = [
  path("", views.facility_list, name="list"),
  path("rooms/<int:room_id>/status/", views.room_status,name="room_status"),
    path("machines/<int:machine_id>/status/",views.machine_status, name="machine_status"),
]