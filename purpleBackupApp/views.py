from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Q
from django.http import HttpResponseRedirect, JsonResponse, Http404, FileResponse
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.db.models.functions import Length, Replace
from django.conf import settings
import os
from urllib.parse import quote

from .models import WasabiBucket, FileBackup
from .tasks import trigger_incremental_backup, backup_all_buckets
from celery.result import AsyncResult
from backupProject.celery import app  # your Celery app
import humanize  # for human-readable sizes


def dashboard(request):
    
    buckets = WasabiBucket.objects.all()
    total_buckets = buckets.count()
    total_files = FileBackup.objects.count()
    total_size = FileBackup.objects.aggregate(total=Sum('size'))['total'] or 0
    total_size_hr = humanize.naturalsize(total_size)
    last_backup_time = buckets.order_by('-last_backup_at').first().last_backup_at if buckets.exists() else None

    context = {
        "buckets": buckets,
        "total_buckets": total_buckets,
        "total_files": total_files,
        "total_size": total_size,
        "total_size_hr": total_size_hr,
        "last_backup_time": last_backup_time,
    }
    return render(request, "purpleBackupApp/dashboard.html", context)


def buckets(request):
    """Buckets view showing all buckets with backup functionality"""
    buckets = WasabiBucket.objects.all()
    total_buckets = buckets.count()
    total_files = FileBackup.objects.count()
    total_size = FileBackup.objects.aggregate(total=Sum('size'))['total'] or 0
    total_size_hr = humanize.naturalsize(total_size)

    context = {
        "buckets": buckets,
        "total_buckets": total_buckets,
        "total_files": total_files,
        "total_size": total_size,
        "total_size_hr": total_size_hr,
    }
    return render(request, "purpleBackupApp/buckets.html", context)


def home(request):
    """Redirect home to dashboard"""
    return dashboard(request)


from django.shortcuts import get_object_or_404, render
from django.db.models import Sum
from .models import WasabiBucket, FileBackup

def format_bytes(size):
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def bucket_detail(request, bucket_id):
    bucket = get_object_or_404(WasabiBucket, id=bucket_id)
    current_folder = request.GET.get('folder', '').strip('/')

    # All files under the current folder recursively
    if current_folder:
        files_in_folder = bucket.files.filter(wasabi_key__startswith=current_folder + '/')
    else:
        files_in_folder = bucket.files.all()

    # Compute stats for the folder recursively
    total_objects = files_in_folder.count()
    total_data = files_in_folder.aggregate(total_size=Sum('size'))['total_size'] or 0
    total_data_hr = format_bytes(total_data)

    # Determine immediate subfolders (next level only)
    subfolders = set()
    immediate_files = []
    for f in files_in_folder:
        parts = f.wasabi_key.split('/')
        if current_folder:
            rel_parts = parts[len(current_folder.split('/')):]
        else:
            rel_parts = parts
        if len(rel_parts) > 1:
            subfolders.add(rel_parts[0])
        else:
            immediate_files.append(f) 

    context = {
        'bucket': bucket,
        'files_qs': immediate_files,  
        'subfolders': sorted(subfolders),
        'current_folder': current_folder,
        'total_objects': total_objects,
        'total_data': total_data,
        'total_data_hr': total_data_hr,
    }

    return render(request, 'purpleBackupApp/bucket_detail.html', context)


def trigger_backup(request, bucket_id=None):
    if request.method == "POST":
        if bucket_id:
            bucket = get_object_or_404(WasabiBucket, id=bucket_id)
            result = trigger_incremental_backup.delay(bucket.id)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"task_id": result.id})
            messages.success(request, f"Backup triggered for {bucket.name} (task id: {result.id})")
            return HttpResponseRedirect(reverse('buckets'))
        else:
            result = backup_all_buckets.delay()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"task_id": result.id})
            messages.success(request, f"Global backup triggered (task id: {result.id})")
            return HttpResponseRedirect(reverse('dashboard'))
    return render(request, "purpleBackupApp/trigger_backup.html")


def trigger_backup_all(request):
    """AJAX trigger global backup"""
    if request.method == "POST":
        result = backup_all_buckets.apply_async()
        return JsonResponse({"task_id": result.id})
    return JsonResponse({"error": "Invalid request"}, status=400)


def backup_status(request, task_id):
    """Check backup task status"""
    try:
        task_result = AsyncResult(task_id, app=app)
        return JsonResponse({
            'status': task_result.state,
            'result': task_result.result
        })
    except Exception as e:
        return JsonResponse({'status': 'ERROR', 'error': str(e)})


def search_files(request):
    """Search files across buckets"""
    query = request.GET.get('q')
    bucket_id = request.GET.get('bucket_id')
    files = FileBackup.objects.none()
    if query:
        files = FileBackup.objects.filter(
            Q(wasabi_key__icontains=query) |
            Q(bucket__name__icontains=query)
        )
        if bucket_id:
            files = files.filter(bucket_id=bucket_id)
    return render(request, "purpleBackupApp/search_results.html", {
        "files": files,
        "query": query,
        "bucket_id": bucket_id
    })


def serve_file(request, file_id):
    """Serve a file from local_path stored in FileBackup"""
    try:
        f = FileBackup.objects.get(id=file_id)
        if not os.path.exists(f.local_path):
            raise Http404("File not found on server.")
        return FileResponse(open(f.local_path, 'rb'), as_attachment=False)
    except FileBackup.DoesNotExist:
        raise Http404("File not found.")


def build_hierarchy(files):
    tree = {}
    for f in files:
        parts = f.wasabi_key.split('/')
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # This is the file
                current[part] = {
                    'wasabi_key': f.wasabi_key,
                    'size': f.size,
                    'url': reverse('serve_file', args=[f.id])
                }
            else:
                # Folder
                if part not in current:
                    current[part] = {}
                if '_size' not in current[part]:
                    current[part]['_size'] = 0
                current[part]['_size'] += f.size
                current = current[part]
    return tree



@csrf_exempt
def stop_backup(request, bucket_id):
    if request.method == "POST":
        return JsonResponse({"status": f"Stop backup requested for bucket {bucket_id}"})
    return JsonResponse({"error": "Invalid request"}, status=400)  