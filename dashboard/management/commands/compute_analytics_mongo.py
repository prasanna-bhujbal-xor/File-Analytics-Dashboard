# dashboard/management/commands/compute_analytics_mongo.py
import json
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Count, Sum
from urllib.parse import quote
from django.urls import reverse

from dashboard.models import FileMetadata
from django.utils import timezone

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None


class Command(BaseCommand):
    help = "Compute dashboard analytics and upsert into MongoDB 'analytics' collection."

    def handle(self, *args, **options):
        if MongoClient is None:
            self.stderr.write("pymongo not installed. Run: pip install pymongo")
            return

        uri = getattr(settings, "MONGO_URI", None)
        db_name = getattr(settings, "MONGO_DB_NAME", None)
        if not uri or not db_name:
            self.stderr.write("MONGO_URI or MONGO_DB_NAME not configured in settings.py")
            return

        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.server_info()  # test connection
        except Exception as e:
            self.stderr.write(f"Could not connect to MongoDB: {e}")
            return

        db = client[db_name]
        coll = db.get_collection("analytics")

        # Compute aggregates using Django ORM (SQL)
        all_files = FileMetadata.objects.all()

        total_files = all_files.count()
        total_size = all_files.aggregate(total_size=Sum('file_size'))['total_size'] or 0

        # file type distribution
        file_type_distribution = list(
            all_files.values('file_type').annotate(count=Count('file_type')).order_by('-count')
        )

        # user contributions (top 20)
        user_contribs = list(
            all_files.values('uploaded_by__username').annotate(count=Count('id')).order_by('-count')[:20]
        )

        # hot files (top by access_count; subject to boundaries in settings)
        min_access = getattr(settings, 'HOT_FILES_MIN_ACCESS', 2)
        max_hot = getattr(settings, 'HOT_FILES_MAX', 10)
        hot_qs = all_files.filter(access_count__gte=min_access).order_by('-access_count', '-last_modified_date')[:max_hot]

        hot_files = []
        for f in hot_qs:
            try:
                rel = f.file_name
                file_url = reverse('serve-shared-file', kwargs={'rel_path': quote(rel, safe='')})
            except Exception:
                file_url = None
            hot_files.append({
                'id': f.id,
                'file_name': f.file_name,
                'file_type': f.file_type,
                'access_count': f.access_count or 0,
                'modified_by_username': f.modified_by.username if f.modified_by else None,
                'last_modified_date': f.last_modified_date,
                'file_url': file_url,
            })

        # recent uploads (latest 20)
        recent_uploads = list(all_files.order_by('-upload_date')[:20].values(
            'id', 'file_name', 'uploaded_by__username', 'upload_date', 'file_size'
        ))

        # top contributors (alias of user_contribs)
        top_contributors = [{'username': u.get('uploaded_by__username'), 'uploads': u.get('count')} for u in user_contribs]

        # Build doc for "global" (team_id None)
        timestamp = timezone.now()
        doc_global = {
            'team_id': None,
            'computed_at': timestamp,
            'total_files': total_files,
            'total_size': total_size,
            'file_type_distribution': file_type_distribution,
            'user_contributions': user_contribs,
            'hot_files': hot_files,
            'recent_uploads': recent_uploads,
            'top_contributors': top_contributors
        }

        # Upsert global doc
        coll.update_one({'team_id': None}, {'$set': doc_global}, upsert=True)
        self.stdout.write(self.style.SUCCESS("Wrote global analytics to MongoDB."))

        # Also write per-team documents (if you want per-team analytics)
        teams = all_files.values('team').distinct()
        for t in teams:
            team_id = t.get('team')
            if team_id is None:
                continue
            team_qs = all_files.filter(team__id=team_id)
            total_files_t = team_qs.count()
            total_size_t = team_qs.aggregate(total_size=Sum('file_size'))['total_size'] or 0
            file_types_t = list(team_qs.values('file_type').annotate(count=Count('file_type')).order_by('-count'))
            user_contribs_t = list(team_qs.values('uploaded_by__username').annotate(count=Count('id')).order_by('-count')[:20])
            hot_qs_t = team_qs.filter(access_count__gte=min_access).order_by('-access_count', '-last_modified_date')[:max_hot]
            hot_files_t = []
            for f in hot_qs_t:
                try:
                    rel = f.file_name
                    file_url = reverse('serve-shared-file', kwargs={'rel_path': quote(rel, safe='')})
                except Exception:
                    file_url = None
                hot_files_t.append({
                    'id': f.id,
                    'file_name': f.file_name,
                    'file_type': f.file_type,
                    'access_count': f.access_count or 0,
                    'modified_by_username': f.modified_by.username if f.modified_by else None,
                    'last_modified_date': f.last_modified_date,
                    'file_url': file_url,
                })

            doc_team = {
                'team_id': team_id,
                'computed_at': timestamp,
                'total_files': total_files_t,
                'total_size': total_size_t,
                'file_type_distribution': file_types_t,
                'user_contributions': user_contribs_t,
                'hot_files': hot_files_t,
                'recent_uploads': list(team_qs.order_by('-upload_date')[:20].values('id','file_name','uploaded_by__username','upload_date','file_size')),
                'top_contributors': [{'username': u.get('uploaded_by__username'), 'uploads': u.get('count')} for u in user_contribs_t]
            }
            coll.update_one({'team_id': team_id}, {'$set': doc_team}, upsert=True)
            self.stdout.write(self.style.SUCCESS(f"Wrote analytics for team {team_id}"))

        self.stdout.write(self.style.SUCCESS("All done. Verify collection 'analytics' in MongoDB Compass."))
