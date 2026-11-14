from django.contrib import admin

from .models import SupportRequest


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
  list_display = ["id", "order", "category", "status", "created_at"]
  list_filter = ["status", "category"]
  search_fields = ["order__quote__customer__email", "description"]
  readonly_fields = ["order", "category", "description", "created_at"]
  fields = ["order", "category", "description", "created_at", "status"]
  ordering = ["-created_at", "-pk"]

  # Staff can resolve reports, while preserving the customer's original account.
  def has_add_permission(self, request):
    return False

  def has_delete_permission(self, request, obj=None):
    return False
