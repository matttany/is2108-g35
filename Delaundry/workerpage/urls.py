from django.urls import path

from . import views

app_name = "workerpage"

urlpatterns = [
  path("tasks/", views.task_board, name="task_board"),
  path("tasks/<int:order_id>/accept/", views.accept_task,name="accept_task"),
]