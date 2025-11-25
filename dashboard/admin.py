from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import FileMetadata, Team, UserProfile

admin.site.register(FileMetadata)
admin.site.register(Team)

#Inline for UserProfile to integrate with User admin
class UserProfileInline(admin.StackedInline):
    model=UserProfile
    can_delete=False
    verbose_name_plural='profile'
    fields = ('team', 'role')

#Extend UserAdmin
class UserAdmin(BaseUserAdmin):
    inlines=(UserProfileInline,)
    list_display=('username','email','first_name','last_name','is_staff','get_team')

    def get_team(self,obj):
        return obj.profile.team.name if hasattr(obj,'profile') and obj.profile.team else '-'
    get_team.short_description='Team'

    def get_role(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.get_role_display() # Get readable role name
        return '-'
    get_role.short_description = 'Role'


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)