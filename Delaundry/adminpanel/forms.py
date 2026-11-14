from django import forms
from django.contrib.auth.forms import AuthenticationForm

from facilities.models import Residence


class StaffLoginForm(AuthenticationForm):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    for field in self.fields.values():
      field.widget.attrs["class"] = "form-control"

  def confirm_login_allowed(self, user):
    super().confirm_login_allowed(user) # Django rejects inactive accounts.
    if not user.is_staff:
      raise forms.ValidationError("Please use a staff account to log in.")


class WorkerFilterForm(forms.Form):
  search = forms.CharField(
    label="Name or NUS email",
    max_length=150,
    required=False,
    widget=forms.TextInput(attrs={"class": "form-control"}),
  )
  residence = forms.ModelChoiceField(
    label="Hall",
    # Include inactive halls so staff can still find their existing workers.
    queryset=Residence.objects.all().order_by("name"),
    empty_label="All halls",
    required=False,
    widget=forms.Select(attrs={"class": "form-select"}),
  )
  approval_status = forms.ChoiceField(
    label="Approval status",
    choices=[
      ("", "All statuses"),
      ("pending", "Pending"),
      ("approved", "Approved"),
      ("suspended", "Suspended"),
    ],
    required=False,
    widget=forms.Select(attrs={"class": "form-select"}),
  )


class WorkerApprovalForm(forms.Form):
  # Staff can approve or suspend, but cannot edit account permissions here.
  approval_status = forms.ChoiceField(
    label="Decision",
    choices=[
      ("", "Select a decision"),
      ("approved", "Approve worker"),
      ("suspended", "Suspend worker"),
    ],
    widget=forms.Select(attrs={"class": "form-select"}),
  )
