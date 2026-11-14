from django.urls import path

from . import views

app_name = "workerpage"

urlpatterns = [
  path("my-tasks/", views.my_tasks, name="my_tasks"),
  path("my-tasks/<int:assignment_id>/progress/", views.task_progress, name="task_progress"),
  path("tasks/", views.task_board, name="task_board"),
  path("tasks/<int:order_id>/accept/", views.accept_task,name="accept_task"),
]
