# dashboard/views.py
import os
import logging
from urllib.parse import unquote, quote
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.db.models import Count, Sum

from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, FormParser
from rest_framework.exceptions import PermissionDenied, ValidationError, APIException

from .models import FileMetadata, UserProfile, Team
from .serializers import FileMetaDataSerializer, UserSerializer
from .utils import scan_shared_folder
from .forms import SignUpForm

from django.urls import reverse

# --- pymongo ---
try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

logger = logging.getLogger(__name__)


# ---------- Basic page views ----------
def home_view(request):
    return render(request, 'dashboard/home.html', context={'greeting': 'Welcome to your File Analytics Dashboard!'})

def about_view(request):
    return render(request, 'dashboard/about.html')

def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html')


# ---------- Helper: resolve safe shared path ----------
def resolve_shared_path(file_name):
    """
    Return absolute filesystem path for a stored file_name (relative path in DB).
    Prevent path traversal by ensuring the resulting path is inside SHARED_FOLDER_PATH.
    """
    base = getattr(settings, 'SHARED_FOLDER_PATH', None)
    if not base:
        raise ValueError("SHARED_FOLDER_PATH not configured in settings.")
    candidate = os.path.normpath(os.path.join(base, file_name))
    base_norm = os.path.normpath(base)
    if not candidate.startswith(base_norm):
        raise ValueError("Invalid file path (possible traversal).")
    return candidate


# ---------- Mongo helpers for analytics ----------
def _get_mongo_collection():
    uri = getattr(settings, "MONGO_URI", None)
    db_name = getattr(settings, "MONGO_DB_NAME", None)
    if not uri or not db_name:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        db = client[db_name]
        return db.get_collection("analytics")
    except Exception:
        return None


# ---------- File list + create ----------
class FileListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = FileMetaDataSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Everyone can read all files (you can restrict to team if desired)
        return FileMetadata.objects.all().order_by('-upload_date')

    def perform_create(self, serializer):
        user = self.request.user
        if not hasattr(user, 'profile') or not user.profile.team:
            raise PermissionDenied("User must belong to a team to upload files.")

        # The serializer was validated by the view — the uploaded file object is in serializer.validated_data['file']
        file_obj = serializer.validated_data.pop('file', None)
        if file_obj is None:
            raise ValidationError("No 'file' field provided in upload.")

        # Sanitize file name
        original_name = file_obj.name
        safe_name = get_valid_filename(original_name)
        base = getattr(settings, 'SHARED_FOLDER_PATH', None)
        if not base:
            raise APIException("Server shared folder not configured (SHARED_FOLDER_PATH).")

        # Construct absolute target path
        target_abs = os.path.abspath(os.path.join(base, safe_name))
        base_abs = os.path.abspath(base)

        # Prevent path traversal
        if not target_abs.startswith(base_abs):
            raise PermissionDenied("Invalid file path.")

        # If exists, append a timestamp suffix to avoid overwrite (or change policy to overwrite)
        if os.path.exists(target_abs):
            name, ext = os.path.splitext(safe_name)
            stamp = timezone.now().strftime("%Y%m%d%H%M%S")
            safe_name = f"{name}_{stamp}{ext}"
            target_abs = os.path.join(base_abs, safe_name)

        # Ensure folder exists
        os.makedirs(os.path.dirname(target_abs), exist_ok=True)

        # Write file to disk in chunks (Django UploadedFile supports chunks())
        try:
            with open(target_abs, 'wb') as fh:
                for chunk in file_obj.chunks():
                    fh.write(chunk)
        except Exception as e:
            raise APIException(f"Failed to save file on server: {e}")

        # Prepare metadata
        file_size = os.path.getsize(target_abs)
        file_type = os.path.splitext(safe_name)[1].lower().lstrip('.')
        last_modified = timezone.now()

        # Save the DB record using serializer.save with explicit fields
        serializer.save(
            uploaded_by=user,
            team=user.profile.team,
            modified_by=user,
            file_name=safe_name,
            file_size=file_size,
            file_type=file_type,
            last_modified_date=last_modified
        )


# ---------- File detail / update / delete ----------
class FileDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FileMetaDataSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FileMetadata.objects.all()

    def perform_update(self, serializer):
        # Save with modified_by set to the current user
        serializer.save(modified_by=self.request.user, last_modified_date=timezone.now())

    def perform_destroy(self, instance):
        user = self.request.user
        if not (hasattr(user, 'profile') and user.profile.team and user.profile.role == 'manager' and instance.team == user.profile.team):
            raise PermissionDenied(detail="Only team manager may delete this file.")
        # Optionally also delete the file from disk
        try:
            full_path = resolve_shared_path(instance.file_name)
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass
        instance.delete()


# ---------- Analytics / Dashboard ----------
class DashboardAnalyticsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):

        # Fallback to SQL computation (REAL-TIME DATA)
        all_files = FileMetadata.objects.all()
        total_files = all_files.count()
        total_size = all_files.aggregate(total_size=Sum('file_size'))['total_size'] or 0

        file_type_distribution = (
            all_files.values('file_type')
            .annotate(count=Count('file_type'))
            .order_by('-count')
        )

        # User contributions for chart
        user_contributions = (
            all_files.values('uploaded_by__username')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Configure Hot Files threshold (set lower for testing/demo visibility)
        min_access = getattr(settings, 'HOT_FILES_MIN_ACCESS', 1) 
        max_hot = getattr(settings, 'HOT_FILES_MAX', 10)

        hot_qs = (
            all_files
            .filter(access_count__gte=min_access)
            .order_by('-access_count', '-last_modified_date')[:max_hot]
        )

        hot_files = []
        for f in hot_qs:
            try:
                file_url = request.build_absolute_uri(
                    reverse('serve-shared-file', kwargs={'rel_path': quote(f.file_name, safe='')})
                )
            except Exception:
                file_url = None

            hot_files.append({
                'id': f.id,
                'file_name': f.file_name,
                'file_type': f.file_type,
                'access_count': f.access_count,
                'modified_by_username': f.modified_by.username if f.modified_by else None,
                'last_modified_date': f.last_modified_date,
                'file_url': file_url,
            })

        # Recent uploads for list
        recent_uploads = []

        data = {
            'total_files': total_files,
            'total_size': total_size,
            'file_type_distribution': list(file_type_distribution),
            'user_contributions': list(user_contributions),
            'hot_files': hot_files,
            'computed_at': timezone.now().isoformat()
        }
        return Response(data, status=status.HTTP_200_OK)


# ---------- Current user details (team members) ----------
class CurrentUserAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        team = None
        if hasattr(user, 'profile'):
            team = user.profile.team

        team_members_data = []
        if team:
            team_members = User.objects.filter(profile__team=team)
            team_members_data = UserSerializer(team_members, many=True).data

        current_user_data = UserSerializer(user).data
        response_data = {
            'user': current_user_data,
            'team_members': team_members_data
        }
        return Response(response_data)


# ---------- Signup ----------
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})


# ---------- Rescan shared folder (manager-only) ----------
class RescanSharedFolderAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not hasattr(user, 'profile') or user.profile.role != 'manager':
            return Response({'detail': 'Only managers can rescan.'}, status=403)
        try:
            stats = scan_shared_folder(root_path=getattr(settings, 'SHARED_FOLDER_PATH', None), create_missing=True)
        except Exception as e:
            return Response({'detail': f'Scan failed: {str(e)}'}, status=500)
        return Response({'detail': 'Rescan complete.', 'stats': stats}, status=200)


# ---------- File access endpoint (increment access_count) ----------
class FileAccessAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        file_obj = get_object_or_404(FileMetadata, pk=pk)
        # Increment count
        file_obj.access_count = (file_obj.access_count or 0) + 1
        file_obj.save(update_fields=['access_count'])
        return Response({'id': file_obj.id, 'access_count': file_obj.access_count}, status=status.HTTP_200_OK)


# ---------- Serve shared file (safe) ----------
def serve_shared_file(request, rel_path):
    rel_path = unquote(rel_path)
    base = os.path.abspath(getattr(settings, 'SHARED_FOLDER_PATH', '') or '')
    if not base:
        raise Http404("Shared folder not configured")

    safe_path = os.path.abspath(os.path.join(base, rel_path))
    if not safe_path.startswith(base):
        raise Http404("Invalid file path")

    if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
        raise Http404("File not found")

    # Stream file back — as_attachment False so it opens in-browser for viewable types
    return FileResponse(open(safe_path, 'rb'), as_attachment=False, filename=os.path.basename(safe_path))


# ---------- File content view (editor) ----------
EDITABLE_EXT = {"txt", "csv", "md", "py", "json", "html", "js", "css", "log", "docx"}
MAX_EDIT_SIZE = getattr(settings, "MAX_EDIT_SIZE_BYTES", 2 * 1024 * 1024)

class FileContentAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [FormParser, JSONParser]

    def get(self, request, pk, *args, **kwargs):
        file_obj = get_object_or_404(FileMetadata, pk=pk)
        user = request.user
        if not (hasattr(user, 'profile') and user.profile.team and file_obj.team == user.profile.team):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        ext = (file_obj.file_type or "").lower()
        if ext not in EDITABLE_EXT:
            return Response({'detail': f'File type .{ext} is not editable in-browser.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            full_path = resolve_shared_path(file_obj.file_name)
            size = os.path.getsize(full_path)
            if size > MAX_EDIT_SIZE:
                return Response({'detail': 'File is too large to edit in-browser.'}, status=status.HTTP_400_BAD_REQUEST)

            with open(full_path, 'rb') as fh:
                raw = fh.read()
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = raw.decode('latin-1')
            return Response({'file_name': file_obj.file_name, 'content': text, 'size': size}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': f'Could not read file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, pk, *args, **kwargs):
        file_obj = get_object_or_404(FileMetadata, pk=pk)
        user = request.user
        if not (hasattr(user, 'profile') and user.profile.team and file_obj.team == user.profile.team):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get('content', None)
        if content is None:
            return Response({'detail': 'Missing content.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            full_path = resolve_shared_path(file_obj.file_name)
            with open(full_path, 'wb') as fh:
                fh.write(content.encode('utf-8'))

            file_obj.file_size = os.path.getsize(full_path)
            file_obj.last_modified_date = timezone.now()
            file_obj.modified_by = user
            file_obj.save(update_fields=['file_size', 'last_modified_date', 'modified_by'])

            return Response({'detail': 'Saved.'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': f'Could not save file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)