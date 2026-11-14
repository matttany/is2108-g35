from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.contrib.auth.forms import AuthenticationForm

from facilities.models import Residence
from .models import User, CustomerProfile

class CustomerRegistrationForm(UserCreationForm):
    email = forms.EmailField(max_length=150)

    residence = forms.ModelChoiceField(
        queryset=Residence.objects.filter(is_active=True), # dropdown for 6 halls
        empty_label="Select your residence",
    )
    unit_number = forms.CharField(
      max_length=8,
      widget=forms.TextInput(
        attrs={"placeholder": "Eg. #01-01"},
        ),
    )

    password1 = forms.CharField(
        label="Enter Password",
        strip=False,
        # PasswordInput masks input field when typing
        widget=forms.PasswordInput(
          render_value=True, # keeps password if validation fails
          attrs={"autocomplete": "new-password"}),
    )

    password2 = forms.CharField(
            label="Confirm your password",
            strip=False,
            # PasswordInput masks input field when typing
            widget=forms.PasswordInput(
              render_value=True,
              attrs={"autocomplete": "new-password"}),
        )

    class Meta:
      model = User
      fields = [
        "name",
        "email",
        "residence",
        "unit_number",
        "password1",
        "password2",
      ]

    def clean_email(self):
      email = self.cleaned_data["email"].strip().lower() # standardise all lower case + no spaces

      if email.split("@")[1] != "u.nus.edu":
        raise forms.ValidationError("Please enter a valid NUS email address.")

      if (User.objects.filter(email=email).exists()):
        raise forms.ValidationError("This email address is already in use. Please use a different email address.")

      return email

    @transaction.atomic 
    # user and customerprofile saved tgt or not at all
    def save(self): 
      user = super().save(commit=False)
      # preps user using form but doesnt save to db yet
      email = self.cleaned_data["email"].strip().lower()
      user.email = email
      user.username = email.split("@")[0] # student id as username
      user.role = "customer"
      user.save() 

      CustomerProfile.objects.create(
          user=user,
          residence=self.cleaned_data["residence"],
          unitNum=self.cleaned_data["unit_number"],
      )

      return user


class CustomerLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="NUS Email",
        max_length=150,
        widget=forms.TextInput(
            attrs={
              "autocomplete": "username",
              "placeholder": "Eg. e1234567@u.nus.edu",
            },
        )
    )

    password = forms.CharField(
      label="Password",
      strip=False,
      widget=forms.PasswordInput(
        attrs={"autocomplete": "current-password"},
      ),
      )

    def clean_username(self):
      email = self.cleaned_data["username"].strip().lower()
      identifier, domain = email.split("@")

      if domain != "u.nus.edu":
        raise forms.ValidationError(
          "Please enter a valid NUS email address."
        )

      return identifier

    # separate login pages for customer and staff eventually
    def confirm_login_allowed(self, user):
      super().confirm_login_allowed(user) # is_active must be true

      if user.role != "customer":
        raise forms.ValidationError(
          "Please use a customer account to log in.",
          code="invalid_role",
        )
