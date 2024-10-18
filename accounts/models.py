# bnbu_backend_api/account/models.py
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('admin', 'Admin User'),      # Admin only managed via admin panel
        ('research', 'Research User'),
        ('coach', 'Coach User'),
        ('client', 'Client User'),
    )

    NON_ADMIN_USER_TYPE_CHOICES = (
        ('research', 'Research User'),
        ('coach', 'Coach User'),
        ('client', 'Client User'),
    )

    user_type = models.CharField(max_length=50, choices=USER_TYPE_CHOICES, default='client')

    def __str__(self):
        return self.username

    objects = UserManager()
