from django.db import models
import hashlib
class WasabiBucket(models.Model):
    name = models.CharField(max_length=191, unique=True)  # actual bucket name
    display_name = models.CharField(max_length=255, blank=True, null=True)  # optional human-friendly name
    prefix_1 = models.CharField(max_length=255, blank=True, null=True)
    prefix_2 = models.CharField(max_length=255, blank=True, null=True)
    
    
    # Backup tracking
    last_backup_completed = models.BooleanField(default=False)
    last_backup_at = models.DateTimeField(blank=True, null=True)
    successful_backups = models.PositiveIntegerField(default=0)
    failed_backups = models.PositiveIntegerField(default=0)

    # Stats (precomputed)
    total_files = models.PositiveBigIntegerField(default=0)
    total_size = models.BigIntegerField(default=0)  # in bytes

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.name


class FileBackup(models.Model):
    STATUS_CHOICES = [
        ('synced', 'Synced'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ]

    # Wasabi details
    bucket = models.ForeignKey(WasabiBucket, on_delete=models.CASCADE, related_name='files')
    wasabi_key = models.CharField(max_length=1024,db_index=False)  # full path in bucket
    wasabi_key_hash=models.CharField(max_length=64, unique=True, null=True, blank=True)  # SHA256 hash of wasabi_key for indexing
    etag = models.CharField(max_length=64)  # checksum from Wasabi
    last_modified = models.DateTimeField()  # last modified on Wasabi
    size = models.BigIntegerField()  # file size in bytes
    @property
    def filename(self):
        """
        Returns only the last part of the Wasabi key (the file name)
        """
        return self.wasabi_key.split('/')[-1]

    # Local system details
    local_path = models.CharField(max_length=1024)
    local_etag = models.CharField(max_length=64, blank=True, null=True)
    last_synced = models.DateTimeField(blank=True, null=True)

    # Backup metadata
    batch_id = models.PositiveIntegerField()  # batch counter for incremental backups
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('bucket', 'wasabi_key')  # ensures no duplicate file entries per bucket

    def save(self, *args, **kwargs):
        # Compute SHA256 hash of wasabi_key for indexing
        self.wasabi_key_hash = hashlib.sha256(self.wasabi_key.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bucket.name}/{self.wasabi_key}"

class BackupBatch(models.Model):
    bucket = models.ForeignKey(WasabiBucket, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.PositiveIntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    successful_files = models.PositiveIntegerField(default=0)
    failed_files = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('bucket', 'batch_number')

    def __str__(self):
        return f"Batch {self.batch_number} - {self.bucket.name}"

