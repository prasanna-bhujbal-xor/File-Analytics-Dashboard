from django import forms
from django.contrib.auth.forms import UserCreationForm
class FileUploadForm(forms.Form):
    """
    A simple form with a single FileField to handle file uploads.
    """
    file = forms.FileField(
        label='Select a file',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        
        fields = ('username', 'email', 'first_name', 'last_name')