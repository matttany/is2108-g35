from django.shortcuts import redirect, render

from .forms import CustomerRegistrationForm

# for login (c01 for now)
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST

from .forms import CustomerLoginForm

# Create your views here.
def register(request):
  if request.method == "POST":  
    form = CustomerRegistrationForm(request.POST)

    if form.is_valid():
      form.save()
      return redirect("accounts:registration_success")
  else: 
      form = CustomerRegistrationForm() 

  return render(
      request,
      "accounts/register.html",
      {"form": form},
    )

def registration_success(request):
  return render(
    request,
    "accounts/registration_success.html",
  )

def customer_login(request):
  if request.method == "POST":
    form = CustomerLoginForm(
      request=request,
      data=request.POST,
    )

    if form.is_valid():
      login(request, form.get_user())
      return redirect("accounts:customer_home")
  else:
    form = CustomerLoginForm(request=request)

  return render(
    request,
    "accounts/login.html",
    {"form": form},
  )


@login_required(login_url="accounts:login")
def customer_home(request):
  if request.user.role != "customer":
    return HttpResponseForbidden(
      "This page is for customers only. Please use our customer login page to access your account."
    )

  return render(
    request,
    "accounts/customer_home.html",
  )

@require_POST
def customer_logout(request):
  logout(request)
  return redirect("accounts:login")