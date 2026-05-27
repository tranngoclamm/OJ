from django.db import models

class Device(models.Model):
    device_id = models.CharField(max_length=100, db_index=True)

    public_key = models.TextField(unique=True)  # identity thật

    hostname = models.CharField(max_length=100, db_index=True)
    mac = models.CharField(max_length=50)

    room = models.ForeignKey(
        "judge.Room",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="devices"
    )

    is_active = models.BooleanField(default=True)

    last_ip = models.GenericIPAddressField(null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.hostname
        
    class Meta:
        indexes = [
            models.Index(fields=["device_id"]),
            models.Index(fields=["hostname"]),
        ]

class Room(models.Model):
    code = models.CharField(max_length=20, unique=True)  # A6-501
    name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.code

class ContestSeat(models.Model):
    # contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    contest = models.ForeignKey("judge.Contest", on_delete=models.CASCADE)
    user = models.ForeignKey("judge.Profile", on_delete=models.CASCADE)
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contest", "user"], name="uniq_user_per_contest"),
            models.UniqueConstraint(fields=["contest", "device"], name="uniq_device_per_contest"),
        ]
