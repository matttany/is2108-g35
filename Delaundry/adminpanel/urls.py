from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
  path("", views.dashboard, name="index"),
  path("dashboard/", views.dashboard, name="dashboard"),
  path("reports/", views.report_list, name="report_list"),
  path("reports/<int:report_id>/", views.report_detail, name="report_detail"),
  path("login/", views.staff_login, name="login"),
  path("logout/", views.staff_logout, name="logout"),
  path("workers/", views.worker_list, name="worker_list"),
  path("workers/<int:worker_id>/", views.worker_review, name="worker_review"),
]
