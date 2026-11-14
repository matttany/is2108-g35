from django.urls import path

from . import views

app_name = "workerpage"

urlpatterns = [
  path("tasks/", views.task_board, name="task_board"),
]