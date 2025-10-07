from django.urls import path
from . import views

urlpatterns = [
    # Redirect root to dashboard (or keep home if needed)
    path("", views.dashboard, name="dashboard"),  # Changed from home to dashboard
    path("home/", views.home, name="home"),  # Optional: keep home if needed for backward compatibility
    
    # New pages
    path("dashboard/", views.dashboard, name="dashboard"),
    path("buckets/", views.buckets, name="buckets"),
    
    # Existing routes
    path("bucket/<int:bucket_id>/", views.bucket_detail, name="bucket_detail"),
    path("backup/<int:bucket_id>/", views.trigger_backup, name="trigger_backup"),
    path("backup/all/", views.trigger_backup_all, name="trigger_backup_all"),  # JSON view
    path("backup/status/<str:task_id>/", views.backup_status, name="backup_status"),
    path("search/", views.search_files, name="search_files"),
    path("file/<int:file_id>/", views.serve_file, name="serve_file"),
    path("bucket/<int:bucket_id>/stop-backup/", views.stop_backup, name="stop_backup"),
    # urls.py
   
    
]
