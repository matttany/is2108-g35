from django.shortcuts import redirect, render

from .forms import CustomerRegistrationForm

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