from django.urls import path

from . import views

app_name = "customerstorefront"

urlpatterns = [
  path("orders/", views.order_list, name="order_list"),
  path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
  path("availability/", views.availability, name="availability"),
  path("quotes/<int:quote_id>/", views.quote_detail, name="quote_detail"),
  path("quotes/<int:quote_id>/submit/", views.submit_request, name="submit_request"),
]
