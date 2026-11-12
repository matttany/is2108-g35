from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
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

class CustomerProfile(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  residence = models.ForeignKey('facilities.Residence', on_delete=models.PROTECT)
  
  id = models.AutoField(primary_key=True)
  unitNum = models.CharField(max_length=8)
  phoneNum = models.CharField(max_length=12)
  # pickup note?

class WorkerProfile(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  residence = models.ForeignKey('facilities.Residence', on_delete=models.PROTECT)

  id = models.AutoField(primary_key=True)
  phoneNum = models.CharField(max_length=12)
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
  