from datetime import time, timedelta

from django import forms
from django.utils import timezone

from bookings.availability import BOOKING_DAYS_AHEAD
from bookings.models import SERVICE_START_TIMES, SupportRequest


class SupportRequestForm(forms.ModelForm):
  class Meta:
    model = SupportRequest
    # Order ownership and report status come from the server, not the browser.
    fields = ["category", "description"]
    labels = {"category": "Problem type", "description": "What happened?"}
    widgets = {
      "category": forms.Select(attrs={"class": "form-select"}),
      "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    }
    help_texts = {"description": "Describe the problem in up to 2,000 characters."}


class AvailabilityForm(forms.Form):
  date = forms.DateField(
    label="Laundry date",
    widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
  )
  window_start = forms.TypedChoiceField(
    label="Pickup time",
    choices=[(start.strftime("%H:%M"), start.strftime("%H:%M")) for start in SERVICE_START_TIMES],
    coerce=time.fromisoformat,
    required=False,
    empty_value=None,
  )

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    today = timezone.localdate()
    self.fields["date"].widget.attrs["min"] = today.isoformat()
    self.fields["date"].widget.attrs["max"] = (today + timedelta(days=BOOKING_DAYS_AHEAD)).isoformat()

  def clean_date(self):
    selected_date = self.cleaned_data["date"]
    today = timezone.localdate()
    if selected_date < today:
      raise forms.ValidationError("Please choose today or a future date.")
    if selected_date > today + timedelta(days=BOOKING_DAYS_AHEAD):
      raise forms.ValidationError(f"Please choose a date within the next {BOOKING_DAYS_AHEAD} days.")
    return selected_date
