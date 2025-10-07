import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backupProject.settings")

app = Celery("backupProject")

# ✅ Read broker/result/backend/etc. from Django settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# ✅ Auto-discover tasks from all installed apps
app.autodiscover_tasks()
