from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Prefetch

from .models import Residence, LaundryRoom, Machine

from django.views.decorators.http import require_http_methods

from .forms import LaundryRoomStatusForm, MachineStatusForm 

# Create your views here.
@login_required(login_url="adminpanel:login")
def facility_list(request):
  if not request.user.is_active or not request.user.is_staff:
    return HttpResponseForbidden(
      "This page is for current admin staff only."
    )

  rooms = LaundryRoom.objects.order_by("block").prefetch_related(
    Prefetch(
      "machine_set",
      queryset=Machine.objects.filter(
        machine_type="washer",
      ).order_by("code"),
      to_attr="washers",
    ),
    Prefetch(
      "machine_set",
      queryset=Machine.objects.filter(
        machine_type="dryer",
      ).order_by("code"),
      to_attr="dryers",
    ),
  )

  residences = Residence.objects.order_by("name").prefetch_related(
    Prefetch(
      "laundryroom_set",
      queryset=rooms,
      to_attr="rooms",
    ),
  )

  return render(request, "facilities/facility_list.html", {
    "residences": residences,
  })

@login_required(login_url="adminpanel:login")
@require_http_methods(["GET", "POST"])
def room_status(request, room_id):
  if not request.user.is_active or not request.user.is_staff:
    return HttpResponseForbidden(
      "This page is for current admin staff only."
    )

  room = get_object_or_404(
    LaundryRoom.objects.select_related("residence"),
    pk=room_id,
  )

  if request.method == "POST":
    form = LaundryRoomStatusForm(request.POST, instance=room)

    if form.is_valid():
      form.save()
      return redirect("facilities:list")
    
  else:
    form = LaundryRoomStatusForm(instance=room)

  return render(request, "facilities/room_status.html", {
    "form": form,
    "room": room,
  })

@login_required(login_url="adminpanel:login")
@require_http_methods(["GET", "POST"])
def machine_status(request, machine_id):
  if not request.user.is_active or not request.user.is_staff:
    return HttpResponseForbidden(
      "This page is for current admin staff only."
    )

  machine = get_object_or_404(
    Machine.objects.select_related("laundry_room__residence"),
    pk=machine_id,
  )

  if request.method == "POST":
    form = MachineStatusForm(request.POST, instance=machine)

    if form.is_valid():
      form.save()
      return redirect("facilities:list")
  else:
    form = MachineStatusForm(instance=machine)

  return render(request, "facilities/machine_status.html", {
    "form": form,
    "machine": machine,
  })