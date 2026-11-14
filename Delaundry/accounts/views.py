from django.shortcuts import redirect, render

from .forms import CustomerRegistrationForm

# for login (c01 for now)
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST

from .forms import CustomerLoginForm
from .forms import WorkerRegistrationForm, WorkerLoginForm
from .models import WorkerProfile
from django.db import IntegrityError

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


def worker_register(request):
  if request.method == "POST":
    form = WorkerRegistrationForm(request.POST)
    if form.is_valid():
      try:
        form.save()
      except IntegrityError:
        # Another registration may have taken the email while this form was open.
        form.add_error(None, "We could not create this account. Please check whether you have already registered.")
      else:
        return redirect("accounts:worker_registration_success")
  else:
    form = WorkerRegistrationForm()

  return render(request, "accounts/worker_register.html", {"form": form})


def worker_registration_success(request):
  return render(request, "accounts/worker_registration_success.html")


def worker_login(request):
  if request.method == "POST":
    form = WorkerLoginForm(request=request, data=request.POST)
    if form.is_valid():
      login(request, form.get_user())
      return redirect("accounts:worker_home")
  else:
    form = WorkerLoginForm(request=request)

  return render(request, "accounts/worker_login.html", {"form": form})


@login_required(login_url="accounts:worker_login")
def worker_home(request):
  if request.user.role != "worker":
    return HttpResponseForbidden("This page is for laundry workers only.")

  profile = WorkerProfile.objects.filter(user=request.user).first()
  if profile is None:
    return HttpResponseForbidden("Your worker profile is missing. Please contact staff.")

  context = {"profile": profile, "can_accept_jobs": profile.can_accept_jobs()}
  return render(request, "accounts/worker_home.html", context)


@require_POST
def worker_logout(request):
  logout(request)
  return redirect("accounts:worker_login")
