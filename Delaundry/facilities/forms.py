from django import forms

from .models import LaundryRoom, Machine


class LaundryRoomStatusForm(forms.ModelForm):
  
  class Meta:
    model = LaundryRoom
    fields = ["is_active"]
    labels = {
      "is_active": "Room available for new bookings",
    }
    widgets = {
      "is_active": forms.CheckboxInput(
        attrs={"class": "form-check-input"},
      ),
    }

class MachineStatusForm(forms.ModelForm):
  class Meta:
    model = Machine
    fields = ["status"]
    labels = {
      "status": "Machine availability",
    }
    widgets = {
      "status": forms.Select(
        attrs={"class": "form-select"},
      ),
    }