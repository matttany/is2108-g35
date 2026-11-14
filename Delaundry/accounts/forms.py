from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.validators import UnicodeUsernameValidator

from facilities.models import Residence
from .models import User, CustomerProfile, WorkerProfile

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


class WorkerRegistrationForm(UserCreationForm):
    email = forms.EmailField(label="NUS email", max_length=150)
    residence = forms.ModelChoiceField(
        label="Hall",
        queryset=Residence.objects.filter(is_active=True),
        empty_label="Select your hall",
    )

    class Meta:
        model = User
        fields = ["name", "email", "residence", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-select" if name == "residence" else "form-control"
        self.fields["name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].widget.attrs["autocomplete"] = "email"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        username, domain = email.rsplit("@", 1)

        if domain != "u.nus.edu":
            raise forms.ValidationError("Please enter a valid NUS email address.")

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already in use.")

        # Customer accounts also use the email prefix as their username.
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("An account already uses this student email identifier.")

        # The email prefix must also be a valid Django username.
        UnicodeUsernameValidator()(username)
        self.instance.username = username
        return email

    @transaction.atomic
    def save(self):
        # Save both records together; UserCreationForm hashes the password.
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email.split("@")[0]
        user.role = "worker"
        user.save()

        WorkerProfile.objects.create(
            user=user,
            residence=self.cleaned_data["residence"],
            approval_status="pending", # Only staff can approve an application.
        )
        return user


class WorkerLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="NUS email",
        max_length=150,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}),
    )

    def clean_username(self):
        email = self.cleaned_data["username"].strip().lower()
        username, domain = email.rsplit("@", 1)
        if domain != "u.nus.edu":
            raise forms.ValidationError("Please enter a valid NUS email address.")
        return username

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user) # Inactive accounts cannot log in.
        if user.role != "worker" or not WorkerProfile.objects.filter(user=user).exists():
            raise forms.ValidationError("Please use a laundry-worker account to log in.")
        # Pending and suspended workers may log in to check their status.
