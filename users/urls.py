from django.urls import path, include
from . import views, forms
from django.contrib.auth import views as auth_views
from django.urls import re_path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
urlpatterns = [
     path('register/', views.RegisterView.as_view(), name='users-register'), 

     path('login/', views.CustomLoginView.as_view(redirect_authenticated_user=True, template_name='users/login.html',
                                        authentication_form=forms.LoginForm), name='login'),
     re_path(r'^oauth/', include('social_django.urls', namespace='social')),
                                   
     path('logout/', views.logout_view, name='logout'),
     path('password-reset/', views.ResetPasswordView.as_view(), name='password-reset'),

     path('password-change/', views.custom_password_change, name='password-change'),  
     path('password_change/done/', views.password_change_done, name='password-change-done'),

     path('account/', views.account, name='account-settings'),   
     
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += staticfiles_urlpatterns()