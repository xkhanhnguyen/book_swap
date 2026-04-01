from django.shortcuts import render, redirect 
from django.contrib import messages
from django.views import View

from .forms import RegisterForm
from django.contrib.auth.views import LoginView
from .forms import RegisterForm, LoginForm,  UpdateUserForm, UpdateProfileForm, CustomPasswordChangeForm

from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordResetView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout

from .models import Profile

# password change
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse

class RegisterView(View):
    form_class = RegisterForm
    initial = {'key': 'value'}
    template_name = 'users/register.html'

    # If the request is get, it creates a new instance of an empty form.
    def get(self, request, *args, **kwargs):
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})

    # If the request is post, -- It creates a new instance of the form with the post data.
    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)

        # if the form is valid, process the cleaned form data and save the user to our database.
        if form.is_valid():
            form.save()

            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}')

            return redirect(to='/')

        return render(request, self.template_name, {'form': form})
    

# Class based view that extends from the built in login view to add a remember me functionality
class CustomLoginView(LoginView):
    form_class = LoginForm

    def form_valid(self, form):
        remember_me = form.cleaned_data.get('remember_me')

        if not remember_me:
            # set session expiry to 0 seconds. So it will automatically close the session after the browser is closed.
            self.request.session.set_expiry(0)

            # Set session as modified to force data updates/cookie to be saved.
            self.request.session.modified = True

        # else browser session will be as long as the session cookie time "SESSION_COOKIE_AGE" defined in settings.py
        return super(CustomLoginView, self).form_valid(form)
    

class ResetPasswordView(SuccessMessageMixin, PasswordResetView):
    template_name = 'users/password_reset.html'
    email_template_name = 'users/password_reset_email.html' # the template used for generating the body of the email with the reset password link.
    subject_template_name = 'users/password_reset_subject' # the template used for generating the subject of the email with the reset password link.
    success_message = "We've emailed you instructions for setting your password, " \
                      "if an account exists with the email you entered. You should receive them shortly." \
                      " If you don't receive an email, " \
                      "please make sure you've entered the address you registered with, and check your spam folder."
    # The message that will be displayed upon a successful password reset request.
    success_url = reverse_lazy('users-home') # If not given any, django defaults to 'password_reset_done' after a successful password request.


@login_required
def account(request):
    
    if request.method == 'POST':
        user_form = UpdateUserForm(request.POST, instance=request.user)
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user.profile)

        if user_form.is_valid() and profile_form.is_valid():
            # profile_form = Profile.objects.get_or_create(user=request.user)
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile is updated successfully')
            return redirect(to='users-profile')
    else:
        user_form = UpdateUserForm(instance=request.user)
        profile_form = UpdateProfileForm(instance=request.user.profile)

    return render(request, 'users/account_settings.html', {'user_form': user_form, 'profile_form': profile_form})

@login_required
def custom_password_change(request):
    # Set the redirect URL after the password is successfully changed
    post_change_redirect = reverse_lazy('password-change-done')
    
    # Handle POST request
    if request.method == "POST":
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(post_change_redirect)
    else:
        form = CustomPasswordChangeForm(user=request.user)

    # Pass form to template
    context = {
        'form': form,
    }
    
    return TemplateResponse(request, 'users/password_change.html', context)

def password_change_done(request):
    return render(request, 'users/password_change_done.html')

def logout_view(request):
    auth_logout(request)
    return redirect('/')