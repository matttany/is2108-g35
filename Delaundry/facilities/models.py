from django.db import models

BLOCK_CHOICES = [(block, f"Block {block}") for block in "ABCDEF"]

# Create your models here.
class Residence(models.Model):
  id = models.AutoField(primary_key=True)
  name = models.CharField(
    max_length=120, 
    unique=True,
    choices=[
      ('eusoff', 'Eusoff Hall'),
      ('kentridge', 'Kent Ridge Hall'),
      ('kingedward', 'King Edward VII Hall'),
      ('raffles', 'Raffles Hall'),
      ('sheares', 'Sheares Hall'),
      ('temasek', 'Temasek Hall')
  ])
  is_active = models.BooleanField(default=True) # just for admin control

  def __str__(self):
    return self.get_name_display()


class LaundryRoom(models.Model):
  id = models.AutoField(primary_key=True)
  residence = models.ForeignKey(Residence, on_delete=models.PROTECT)
  block = models.CharField(max_length=120, choices=BLOCK_CHOICES)
  is_active = models.BooleanField(default=True) # just for admin control

  def __str__(self):
    return f"{self.residence} - {self.get_block_display()}"

  class Meta: # prevents duplicate rooms in same block
    constraints = [
        models.UniqueConstraint(
            fields=["residence", "block"],
            name="unique_room_per_residence_block",
        ),
    ]

class Machine(models.Model):
  id = models.AutoField(primary_key=True)
  laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.PROTECT)
  machine_type = models.CharField(max_length=120, choices=[
    ('washer', 'Washer'), 
    ('dryer', 'Dryer')
  ])

  code = models.CharField(max_length=4) #W01, D10, etc
  WASH_CYCLE_MINUTES = 30
  DRY_CYCLE_MINUTES = 30

  status = models.CharField(
    max_length=20,
    choices=[
      ("ACTIVE", "Active"),
      ("OUT_OF_SERVICE", "Out of service"),
    ],
    default="ACTIVE",
  )

  def __str__(self):
    return f"{self.laundry_room} - {self.code}"

  class Meta: # prevents duplicate machine codes in same laundry room, but allows same code in different rooms
    constraints = [
        models.UniqueConstraint(
            fields=["laundry_room", "code"],
            name="unique_machine_code_per_room",
        ),
    ]



