# dashboard/utils.py
import os
import logging
# Use standard lib timezone to avoid Django 5.0 deprecation issues
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count

from .models import FileMetadata, Team

logger = logging.getLogger(__name__)
User = get_user_model()

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

def normalize_relpath(path, base):
    """
    Normalize an absolute 'path' to a relative path under 'base'.
    - Uses os.path.relpath then normalizes separators to forward slashes.
    - Strips leading './'
    """
    base_abs = os.path.abspath(base)
    path_abs = os.path.abspath(path)
    try:
        rel = os.path.relpath(path_abs, base_abs)
    except Exception:
        # fallback if relpath fails
        rel = path_abs.replace(base_abs, '').lstrip(os.path.sep)
    # normalize separators to forward slash for DB consistency
    rel = rel.replace(os.path.sep, '/')
    return rel.lstrip('./')


def scan_shared_folder(root_path=None, create_missing=False, dry_run=False):
    base = os.path.abspath(root_path or getattr(settings, 'SHARED_FOLDER_PATH', '') or '')
    if not base or not os.path.exists(base):
        raise ValueError("Shared folder path not configured or not found: %s" % base)

    stats = {'created': 0, 'updated': 0, 'deleted': 0}
    logger.info("Starting scan_shared_folder for base=%s", base)

    # 1. Build DB map (Case-Insensitive Key)
    # We use .lower() for the key to handle Windows case-insensitivity.
    # This prevents 'File.txt' (disk) vs 'file.txt' (db) from being seen as different.
    db_qs = FileMetadata.objects.all()
    db_map = {}
    for f in db_qs:
        key = (f.file_name or '').replace('\\', '/').lower()
        db_map[key] = f

    # 2. Walk filesystem (Case-Insensitive Key)
    disk_map = {}
    for root, dirs, files in os.walk(base):
        for fname in files:
            full = os.path.join(root, fname)
            rel = normalize_relpath(full, base)
            # Store with lowercase key for lookup, but keep original 'rel' and 'full' for saving
            disk_map[rel.lower()] = {'rel': rel, 'full': full}

    # Threshold to ignore tiny timestamp differences (e.g. 2 seconds)
    THRESHOLD = timedelta(seconds=2)

    # 3. Iterate over Disk Files
    for key_lower, info in disk_map.items():
        rel = info['rel']
        full_path = info['full']

        try:
            fs_mtime = os.path.getmtime(full_path)
            fs_size = os.path.getsize(full_path)
        except OSError:
            logger.warning("Could not stat file: %s", full_path)
            continue

        # Convert disk time to Aware UTC using standard library timezone
        fs_dt = datetime.fromtimestamp(fs_mtime, tz=dt_timezone.utc)

        if key_lower in db_map:
            # File exists in DB (matched case-insensitively)
            db_obj = db_map[key_lower]
            
            # Normalize DB timestamp
            db_last = db_obj.last_modified_date
            if db_last:
                if timezone.is_naive(db_last):
                    db_last = timezone.make_aware(db_last, timezone.get_current_timezone())
                # Use standard library timezone for conversion
                db_last_utc = db_last.astimezone(dt_timezone.utc)
            else:
                db_last_utc = None

            # Only update if the disk file is SIGNIFICANTLY newer than the DB record.
            
            should_update = False
            if db_last_utc is None:
                should_update = True
            elif fs_dt > (db_last_utc + THRESHOLD):
                # Disk is newer by more than 2 seconds -> It's a real external edit
                should_update = True
            
            if should_update:
                if not dry_run:
                    db_obj.last_modified_date = fs_dt
                    db_obj.file_size = fs_size
                    # Only overwrite 'modified_by' because we detected a newer file on disk
                    db_obj.modified_by = None  # Set to System (External Edit)
                    db_obj.save(update_fields=['last_modified_date', 'file_size', 'modified_by'])
                stats['updated'] += 1
            else:
                # Timestamps match (or DB is actually newer). 
                pass

        else:
            # New File Found (creates a new record)
            logger.info("File on disk not in DB: %s", rel)
            if create_missing and not dry_run:
                try:
                    FileMetadata.objects.create(
                        file_name=rel, # Use original casing from disk
                        file_size=fs_size,
                        file_type=os.path.splitext(rel)[1].lower().lstrip('.'),
                        uploaded_by=None, # Unknown uploader (System detected)
                        modified_by=None,
                        last_modified_date=fs_dt,
                        team=None # Admin must assign team later
                    )
                    stats['created'] += 1
                except Exception as e:
                    logger.exception("Failed creating DB entry: %s", e)

    # 4. Check for Deleted Files
    # If it's in the DB map but not in the disk map (checked case-insensitively)
    for key_lower, db_obj in list(db_map.items()):
        if key_lower not in disk_map:
            logger.info("DB entry exists but file missing on disk: %s", db_obj.file_name)
            if not dry_run:
                db_obj.delete()
            stats['deleted'] += 1

    logger.info("Scan finished. stats=%s", stats)
    return stats


def compute_analytics_doc(request=None):
    """
    Compute analytics dict (same format your /api/analytics/ returns).
    Returns a plain dict.
    """
    from .models import FileMetadata 

    all_files = FileMetadata.objects.all()
    total_files = all_files.count()
    total_size = all_files.aggregate(total_size=Sum('file_size'))['total_size'] or 0

    file_type_distribution = list(
        all_files.values('file_type').annotate(count=Count('file_type')).order_by('-count')
    )

    min_access = getattr(settings, 'HOT_FILES_MIN_ACCESS', 1)
    max_hot = getattr(settings, 'HOT_FILES_MAX', 10)

    hot_qs = all_files.filter(access_count__gte=min_access).order_by('-access_count', '-last_modified_date')[:max_hot]
    hot_files = []
    for f in hot_qs:
        try:
            rel = quote(f.file_name or '', safe='')
            from django.urls import reverse
            path = reverse('serve-shared-file', kwargs={'rel_path': rel})
            file_url = (request.build_absolute_uri(path) if request is not None else path)
        except Exception:
            file_url = None

        hot_files.append({
            'id': f.id,
            'file_name': f.file_name,
            'file_type': f.file_type,
            'access_count': f.access_count or 0,
            'modified_by_username': f.modified_by.username if f.modified_by else 'System (external edit)',
            'last_modified_date': f.last_modified_date.isoformat() if f.last_modified_date else None,
            'file_url': file_url,
        })

    doc = {
        'total_files': total_files,
        'total_size': total_size,
        'file_type_distribution': file_type_distribution,
        'hot_files': hot_files,
        'computed_at': timezone.now().isoformat()
    }
    return doc

def write_analytics_to_mongo(doc):
    if MongoClient is None:
        return 

    uri = getattr(settings, 'MONGO_URI', None)
    dbname = getattr(settings, 'MONGO_DB_NAME', 'File_Analytics')
    collname = getattr(settings, 'MONGO_ANALYTICS_COLL', 'dashboard_analytics')

    if not uri:
        return

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        db = client[dbname]
        coll = db[collname]
        coll.replace_one({'_id': 'latest'}, {'_id': 'latest', 'payload': doc, 'updated_at': datetime.utcnow()}, upsert=True)
        client.close()
    except Exception as e:
        logger.error(f"Mongo write failed: {e}")