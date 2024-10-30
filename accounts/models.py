# bnbu_backend_api/account/models.py
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class CustomUserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    for authentication instead of usernames.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('admin', 'Admin User'),
        ('research', 'Research User'),
        ('coach', 'Coach User'),
        ('client', 'Client User'),
        ('general', 'General User'),
    )
    NON_ADMIN_USER_TYPE_CHOICES = (
        ('research', 'Research User'),
        ('coach', 'Coach User'), 
        ('client', 'Client User'),
        ('general', 'General User'),
    )

    user_type = models.CharField(max_length=50, choices=USER_TYPE_CHOICES, default='client')
    is_first_login = models.BooleanField(default=True)

    # Remove the username field, replace it with email
    username = None
    email = models.EmailField(unique=True)  # Set email as unique

    USERNAME_FIELD = 'email'  # Use email for authentication
    REQUIRED_FIELDS = []  # Remove username from required fields

    objects = CustomUserManager()

    def __str__(self):
        return self.email

