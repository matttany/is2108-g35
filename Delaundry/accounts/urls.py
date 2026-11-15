from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
  path("worker/register/", views.worker_register, name="worker_register"),
  path("worker/register/success/", views.worker_registration_success, name="worker_registration_success"),
  path("worker/login/", views.worker_login, name="worker_login"),
  path("worker/home/", views.worker_home, name="worker_home"),
  path("worker/logout/", views.worker_logout, name="worker_logout"),
  path("register/", views.register, name="register"),
  path("register/success/", views.registration_success, name="registration_success"),
  path("login/", views.customer_login, name="login"),
  path("home/", views.customer_home, name="customer_home"),
  path("logout/", views.customer_logout, name="logout"),
]
