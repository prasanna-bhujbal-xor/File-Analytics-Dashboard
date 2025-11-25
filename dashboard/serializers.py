from rest_framework import serializers
from .models import FileMetadata, Team
from django.contrib.auth.models import User
import os
from django.utils import timezone
from django.urls import reverse
from urllib.parse import quote

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model=Team
        fields=['id','name']

class FileMetaDataSerializer(serializers.ModelSerializer):
    uploaded_by_username=serializers.CharField(source="uploaded_by.username", read_only=True)
    modified_by_username = serializers.SerializerMethodField(read_only=True)
    team=TeamSerializer(read_only=True)
    team_id=serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(),source='team', write_only=True, required=False)
    file=serializers.FileField(write_only=True, required=True)
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model=FileMetadata
        fields=[
            'id', 
            'file_name', 
            'file_size', 
            'file_type', 
            'upload_date', 
            'last_modified_date',
            'uploaded_by', 
            'uploaded_by_username',
            'modified_by',
            'modified_by_username',
            'access_count',
            'team',
            'team_id',
            'file',
            'file_url'

        ]

        read_only_fields = [
            'upload_date',
            'uploaded_by',
            'uploaded_by_username',
            'modified_by',
            'modified_by_username',
            'last_modified_date',
            'file_name',
            'file_size',
            'file_type',
            'access_count',
            'file_url',
        ]

        extra_kwargs = {
            'uploaded_by': {'required': False, 'allow_null': True},
            'modified_by': {'required': False, 'allow_null': True},
        }

    def get_modified_by_username(self, obj):
        if obj.modified_by is None:
            #label for external edits
            return 'System (external edit)'
        # if modified_by exists, return username
        return obj.modified_by.username if obj.modified_by else None

    
    # Build a URL for serving the file from the shared folder
    def get_file_url(self, obj):
        """
        Returns a URL path to the serve_shared_file endpoint.
        Uses obj.file_name as the relative path (URL-encoded).
        """
        try:
            if not obj.file_name:
                return None
            rel = quote(obj.file_name, safe='')  # encode spaces/special chars
            return reverse('serve-shared-file', kwargs={'rel_path': rel})
        except Exception:
            return None

    # Handle file upload + metadata extraction

    def create(self, validated_data):
        request = self.context.get('request', None)
        file_obj=validated_data.pop('file',None)
        if file_obj:
            validated_data['file_name']=file_obj.name
            validated_data['file_size']=file_obj.size
            validated_data['file_type']=os.path.splitext(file_obj.name)[1].lower().replace('.','')
            validated_data['last_modified_date'] = timezone.now()

            if request and request.user and request.user.is_authenticated:
                validated_data['modified_by'] = request.user
      
        return FileMetadata.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        """
        Handle replacing file via the 'file' write-only field.
        Called by view.perform_update() which will pass modified_by and last_modified_date.
        """
        file_obj = validated_data.pop('file', None)

        # Update simple writable fields if any were included (e.g., team via team_id)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if file_obj:
            # update file metadata fields from the uploaded File object
            instance.file_name = file_obj.name
            instance.file_size = file_obj.size
            instance.file_type = os.path.splitext(file_obj.name)[1].lower().lstrip('.')
            instance.last_modified_date = timezone.now()
        
            # allow team or other writeable fields 
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
        
    

# This serializer will show user details and their team
class UserSerializer(serializers.ModelSerializer):
    team_name=serializers.CharField(source='profile.team.name', read_only=True, allow_null=True)
    team_id=serializers.IntegerField(source='profile.team.id', read_only=True, allow_null=True )
    role = serializers.CharField(source='profile.get_role_display', read_only=True) 
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'team_name', 'team_id','role']