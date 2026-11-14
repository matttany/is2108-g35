from django import forms

from bookings.delivery import prepare_delivery_photo


class DeliveryProofForm(forms.Form):
  photo = forms.FileField(
    label="Return photo",
    help_text="JPEG or PNG, up to 5 MB and 12 megapixels.",
    widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png"}),
  )
  note = forms.CharField(
    label="Delivery note", required=False, max_length=500,
    widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
  )

  def clean_photo(self):
    return prepare_delivery_photo(self.cleaned_data["photo"])
