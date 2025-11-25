from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os

#Team Model
class Team(models.Model):
    name=models.CharField(max_length=100, unique=True)
    description=models.TextField(blank=True,null=True)

    def __str__(self):
        return self.name

#UserProfile Model (to link User to Team)
#extends the built-in Django User model
class UserProfile(models.Model):
    user=models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    team=models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    role=models.CharField(max_length=50, choices=[('member','Member'),('manager','Manager')], default='member')

    def __str__(self):
        return self.user.username + "Profile"
    

class FileMetadata(models.Model):
    """
    This model stores the metadata for each uploaded file.
    """
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    file_type = models.CharField(max_length=50)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files',null=True,blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)
    last_modified_date = models.DateTimeField()
    team=models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='team_files')
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='modified_files')
    access_count = models.PositiveIntegerField(default=0)

    

    def __str__(self):
        return self.file_name

    def get_file_size_display(self):
        """Returns the file size in a human-readable format (KB, MB, GB)."""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024**2:
            return f"{self.file_size/1024:.2f} KB"
        elif self.file_size < 1024**3:
            return f"{self.file_size/1024**2:.2f} MB"
        else:
            return f"{self.file_size/1024**3:.2f} GB"
        
    class Meta:
        verbose_name_plural= "File Metadata"