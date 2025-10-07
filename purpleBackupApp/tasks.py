from celery import shared_task
from celery.utils.log import get_task_logger
from .models import WasabiBucket, FileBackup
import boto3, os
from django.urls import reverse
from django.conf import settings
from datetime import datetime, timedelta
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import transaction
from django.core.cache import cache


logger = get_task_logger(__name__)

# Wasabi regions and endpoints

WASABI_ENDPOINTS = {
    
    #Asia Pacific
    "ap-northeast-1": "https://s3.ap-northeast-1.wasabisys.com",
    "ap-northeast-2": "https://s3.ap-northeast-2.wasabisys.com",
    "ap-southeast-1": "https://s3.ap-southeast-1.wasabisys.com",
    "ap-southeast-2": "https://s3.ap-southeast-2.wasabisys.com",
    #Canada
    "ca-central-1": "https://s3.ca-central-1.wasabisys.com",
    #Europe
    "eu-central-1": "https://s3.eu-central-1.wasabisys.com",
    "eu-central-2": "https://s3.eu-central-2.wasabisys.com",
    "eu-west-1": "https://s3.eu-west-1.wasabisys.com",
    "eu-south-1": "https://s3.eu-south-1.wasabisys.com",
    "eu-west-2": "https://s3.eu-west-2.wasabisys.com",
    "eu-west-3": "https://s3.eu-west-3.wasabisys.com",

    #US
    "us-east-1": "https://s3.wasabisys.com",
    "us-east-2": "https://s3.us-east-2.wasabisys.com",
    "us-central-1": "https://s3.us-central-1.wasabisys.com",
    "us-west-1": "https://s3.us-west-1.wasabisys.com",
}


CHUNK_SIZE = 500       # DB write batch size
MAX_THREADS = 10       # Max threads for downloading files
def _get_s3_client_for_bucket(bucket_name, access_key, secret_key):
    base_client = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=WASABI_ENDPOINTS["us-east-1"],
        region_name="us-east-1",
    )
    loc = base_client.get_bucket_location(Bucket=bucket_name)
    region = (loc.get("LocationConstraint") or "us-east-1").lower().replace("_", "-")
    endpoint = WASABI_ENDPOINTS.get(region)
    if not endpoint:
        raise Exception(f"Region {region} not in WASABI_ENDPOINTS mapping: {loc}")
    client = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint,
        region_name=region,
    )
    logger.info(f"✅Found bucket {bucket_name} in region {region}")
    return client, region



def _download_file(bucket, s3_client, obj):
    """Download single file and return dict for DB"""
    key = obj["Key"]
    local_path = os.path.join(settings.LOCAL_BACKUP_PATH, bucket.name, key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    s3_client.download_file(bucket.name, key, local_path)
    return {
        "bucket": bucket,
        "wasabi_key": key,
        "etag": obj.get("ETag", "").strip('"'),
        "last_modified": obj["LastModified"],
        "size": obj["Size"],
        "local_path": local_path,
        "status": "synced"
    }


def _bulk_save(records):
    """Batch insert/update DB"""
    objs = [
        FileBackup(
            bucket=r["bucket"],
            wasabi_key=r["wasabi_key"],
            etag=r["etag"],
            last_modified=r["last_modified"],
            size=r["size"],
            local_path=r["local_path"],
            status=r["status"]
        )
        for r in records
    ]
    FileBackup.objects.bulk_create(objs, ignore_conflicts=True)


def _backup_bucket(bucket, s3_client, task=None):
    paginator = s3_client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket.name)

    existing_files = {
        f.wasabi_key: f.etag
        for f in FileBackup.objects.filter(bucket=bucket).only("wasabi_key", "etag")
    }

    total_objs = 0
    completed = 0
    downloaded_records = []

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []

        for page in page_iterator:
            objects = page.get("Contents", [])
            total_objs += len(objects)

            for obj in objects:
                key = obj["Key"]
                if key.endswith("/") and obj["Size"] == 0:
                    completed += 1
                    continue

                etag = obj.get("ETag", "").strip('"')
                if existing_files.get(key) == etag:
                    completed += 1
                    continue

                futures.append(executor.submit(_download_file, bucket, s3_client, obj))

        for future in as_completed(futures):
            record = future.result()
            if record:
                downloaded_records.append(record)
                completed += 1

                cache.set(
                    f"bucket_{bucket.id}_progress",
                    {"total": total_objs, "done": completed, "last_key": record["wasabi_key"]},
                    timeout=3600,
                )

                if len(downloaded_records) >= CHUNK_SIZE:
                    _bulk_save(downloaded_records)
                    downloaded_records = []

    if downloaded_records:
        _bulk_save(downloaded_records)

    cache.delete(f"bucket_{bucket.id}_progress")

    bucket.last_backup_at = timezone.now()
    bucket.last_backup_completed = True
    bucket.successful_backups += 1
    bucket.save(update_fields=["last_backup_at", "last_backup_completed", "successful_backups"])

    logger.info(f"✅ Backup completed for bucket {bucket.name}, total files processed: {total_objs}")
    return total_objs



@shared_task(bind=True)
def trigger_incremental_backup(self, bucket_id):
    """Backup a single bucket"""
    try:
        bucket = WasabiBucket.objects.get(id=bucket_id)
        # pass keys from settings
        s3_client, region = _get_s3_client_for_bucket(
            bucket.name,
            settings.WASABI_ACCESS_KEY,
            settings.WASABI_SECRET_KEY
        )
        total_files = _backup_bucket(bucket, s3_client, task=self)
        return {"status": "completed", "bucket": bucket.name, "files": total_files}
    except Exception as e:
        logger.error(f"❌ Backup failed for bucket {bucket_id}: {e}", exc_info=True)
        raise


@shared_task(bind=True)
def backup_all_buckets(self):
    """Trigger incremental backup for all buckets"""
    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.WASABI_ACCESS_KEY,
            aws_secret_access_key=settings.WASABI_SECRET_KEY,
            endpoint_url=WASABI_ENDPOINTS["us-east-1"],
            region_name="us-east-1",
        )
        response = s3_client.list_buckets()
        buckets = response.get("Buckets", [])

        for b in buckets:
            bucket_obj, _ = WasabiBucket.objects.get_or_create(
                name=b["Name"],
                defaults={"display_name": b["Name"]}
            )
            trigger_incremental_backup.apply_async(args=[bucket_obj.id])

        logger.info(f"✅ Global backup triggered for {len(buckets)} buckets")
        return {"status": "all triggered"}
    except Exception as e:
        logger.error(f"❌ Global backup failed: {e}", exc_info=True)
        raise
