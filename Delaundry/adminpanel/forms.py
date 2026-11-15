from django import forms
from django.contrib.auth.forms import AuthenticationForm

from facilities.models import Residence
from bookings.models import LaundryOrder, SupportRequest


class ReportFilterForm(forms.Form):
  residence = forms.ModelChoiceField(
    label="Hall", queryset=Residence.objects.all().order_by("name"),
    empty_label="All halls", required=False,
    widget=forms.Select(attrs={"class": "form-select"}),
  )
  category = forms.ChoiceField(
    label="Category", required=False,
    choices=[("", "All categories"), *SupportRequest._meta.get_field("category").choices],
    widget=forms.Select(attrs={"class": "form-select"}),
  )
  status = forms.ChoiceField(
    label="Report status", required=False,
    choices=[("", "All statuses"), *SupportRequest._meta.get_field("status").choices],
    widget=forms.Select(attrs={"class": "form-select"}),
  )


class DashboardFilterForm(forms.Form):
  residence = forms.ModelChoiceField(
    label="Hall", queryset=Residence.objects.all().order_by("name"),
    empty_label="All halls", required=False,
    widget=forms.Select(attrs={"class": "form-select"}),
  )
  status = forms.ChoiceField(
    label="Order status", required=False,
    choices=[("", "All statuses"), *LaundryOrder._meta.get_field("status").choices],
    widget=forms.Select(attrs={"class": "form-select"}),
  )
  start_date = forms.DateField(
    label="Submitted from", required=False,
    widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
  )
  end_date = forms.DateField(
    label="Submitted through", required=False,
    widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
  )

  def clean(self):
    data = super().clean()
    start = data.get("start_date")
    end = data.get("end_date")
    if start and end and start > end:
      raise forms.ValidationError("The start date must not be after the end date.")
    return data


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
