from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
  path("register/", views.register, name="register"),
  path("register/success/", views.registration_success, name="registration_success"),
  path("login/", views.customer_login, name="login"),
  path("home/", views.customer_home, name="customer_home"),
  path("logout/", views.customer_logout, name="logout"),
]