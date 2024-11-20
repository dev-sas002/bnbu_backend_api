# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/bnbu_backend_api/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bnbu_backend_api.settings')

app = Celery('bnbu_backend_api')  # Ensure this matches the project name

# Add the configuration for retrying broker connection on startup
app.conf.broker_connection_retry_on_startup = True

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
