from django.contrib import admin
from .models import WasabiBucket, FileBackup
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
from .tasks import trigger_incremental_backup


@admin.register(WasabiBucket)
class WasabiBucketAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "last_backup_completed",
        "last_backup_at",
        "failed_backups",   # instead of consecutive_failed_attempts
        "trigger_backup_button",
    )
    search_fields = ("name",)
    ordering = ("-last_backup_completed",)

    def trigger_backup_button(self, obj):
        """
        Adds a button in the admin list view to trigger backup manually.
        """
        return format_html(
            '<a class="button" href="{}">Trigger Backup</a>',
            reverse("admin:trigger_backup", args=[obj.pk])
        )
    trigger_backup_button.short_description = "Actions"


    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                "trigger-backup/<int:bucket_id>/",
                self.admin_site.admin_view(self.trigger_backup_view),
                name="trigger_backup",
            ),
        ]
        return custom_urls + urls

    def trigger_backup_view(self, request, bucket_id):
        bucket = WasabiBucket.objects.get(pk=bucket_id)
        result = trigger_incremental_backup.delay(bucket.id)
        messages.success(
            request,
            f"Backup triggered for bucket '{bucket.name}' (task id: {result.id})"
        )
        return self.response_post_save_change(request, bucket)


@admin.register(FileBackup)
class FileBackupAdmin(admin.ModelAdmin):
    list_display = (
        "wasabi_key",
        "bucket",
        "local_path",
        "size",
        "created_at",
    )
    list_filter = ("bucket", "created_at")
    search_fields = ("wasabi_key", "bucket__name")
    ordering = ("-created_at",)
