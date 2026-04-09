from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm

from .models import Profile

class RegisterForm(UserCreationForm):
    # fields we want to include and customize in our form
    first_name = forms.CharField(max_length=100,
                                 required=True,
                                 widget=forms.TextInput(attrs={'placeholder': 'First Name',
                                                               'class': 'form-control',
                                                               }))
    last_name = forms.CharField(max_length=100,
                                required=True,
                                widget=forms.TextInput(attrs={'placeholder': 'Last Name',
                                                              'class': 'form-control',
                                                              }))
    username = forms.CharField(max_length=100,
                               required=True,
                               widget=forms.TextInput(attrs={'placeholder': 'Username',
                                                             'class': 'form-control',
                                                             }))
    email = forms.EmailField(required=True,
                             widget=forms.TextInput(attrs={'placeholder': 'Email',
                                                           'class': 'form-control',
                                                           }))
    password1 = forms.CharField(max_length=50,
                                required=True,
                                widget=forms.PasswordInput(attrs={'placeholder': 'Password',
                                                                  'class': 'form-control',
                                                                  'data-toggle': 'password',
                                                                  'id': 'password',
                                                                  }))
    password2 = forms.CharField(max_length=50,
                                required=True,
                                widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password',
                                                                  'class': 'form-control',
                                                                  'data-toggle': 'password',
                                                                  'id': 'password',
                                                                  }))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'password1', 'password2']

class LoginForm(AuthenticationForm):
    username = forms.CharField(max_length=100,
                               required=True,
                               widget=forms.TextInput(attrs={'placeholder': 'Username',
                                                             'class': 'form-control',
                                                             }))
    password = forms.CharField(max_length=50,
                               required=True,
                               widget=forms.PasswordInput(attrs={'placeholder': 'Password',
                                                                 'class': 'form-control',
                                                                 'data-toggle': 'password',
                                                                 'id': 'password',
                                                                 'name': 'password',
                                                                 }))
    remember_me = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ['username', 'password', 'remember_me']



class UpdateUserForm(forms.ModelForm):
    """ update username and email."""
    username = forms.CharField(max_length=100,
                               required=True,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True,
                             widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'email']


class UpdateProfileForm(forms.ModelForm):
    """to let users update their profile"""
    avatar = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-control-file'}), required=False)
    bio = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), required=False)
    address = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 123 Nguyen Hue, District 1, Ho Chi Minh City'}),
        help_text='Private — used only to calculate distance. Never shown to other users.'
    )
    city = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Ho Chi Minh City'}),
        help_text='Shown publicly as your general location (e.g. city name only)'
    )
    # Feature 3: zip code
    zip_code = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 70000'}),
        help_text='Optional ZIP/postal code for location lookup',
    )
    display_preference = forms.ChoiceField(
        choices=[('bookswap_id', 'BookSwap ID (anonymous)'), ('real_name', 'Real Name')],
        widget=forms.RadioSelect(),
        required=True,
    )
    # Feature 8: email notifications
    email_notifications = forms.BooleanField(
        required=False,
        label='Receive email notifications',
        help_text='Get notified by email for swap requests, acceptances, and other activity.',
    )

    class Meta:
        model = Profile
        fields = ['avatar', 'bio', 'address', 'city', 'zip_code', 'display_preference', 'email_notifications']

# Password Change Form
class CustomPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.PasswordInput(attrs={'placeholder': 'Current Password', 'class': 'form-control'})
    )
    new_password1 = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.PasswordInput(attrs={'placeholder': 'New Password', 'class': 'form-control'})
    )
    new_password2 = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm New Password', 'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['old_password', 'new_password1', 'new_password2']
