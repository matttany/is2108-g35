from django.db import models
from django.contrib.auth.models import AbstractUser
from facilities.models import BLOCK_CHOICES

class User(AbstractUser):
  id = models.AutoField(primary_key=True)
  email = models.EmailField(unique=True)
  name = models.CharField(max_length=120)
  role = models.CharField(max_length=120, choices=[('customer', 'Customer'), ('worker', 'Worker')])

  # (creation syntax for later, create_user hashes password)
  # User.objects.create_user(
  #   username="student01",
  #   email="student01@u.nus.edu",
  #   password="example-password",
  #   name="Student One",
  #   role="customer",
  # )

  # contains is_staff (access to built-in admin) and is_superuser (all permissions granted)

class CustomerProfile(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  residence = models.ForeignKey('facilities.Residence', on_delete=models.PROTECT)
  # Existing customers must choose their block before making a new booking.
  block = models.CharField(max_length=1, choices=BLOCK_CHOICES, blank=True, default="")
  
  id = models.AutoField(primary_key=True)
  unitNum = models.CharField(max_length=8)
  # pickup note?

  class Meta:
    constraints = [
      models.CheckConstraint(
        condition=models.Q(block__in=["", *"ABCDEF"]),
        name="customer_valid_block",
      ),
    ]

class WorkerProfile(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  residence = models.ForeignKey('facilities.Residence', on_delete=models.PROTECT)

  id = models.AutoField(primary_key=True)
  is_available = models.BooleanField(default=True)

  # checks whether they are an existing student in nus, will require approval by admin
  approval_status = models.CharField(
    max_length=10,
    choices=[
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("suspended", "Suspended"),
    ],
    default="pending",
  )

  def can_accept_jobs(self):
    # P02/P03 must check this again when browsing or accepting a job.
    return (
      self.user.role == "worker"
      and self.user.is_active
      and self.approval_status == "approved"
      and self.is_available
    )
