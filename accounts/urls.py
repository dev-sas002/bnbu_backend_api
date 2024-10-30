# account/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .forms import EmailAuthenticationForm
from .views import (
    UserListCreateView,
    UserDetailView,  # Add this line
    FirstTimePasswordUpdateView,
    password_change,
    password_reset,
    dashboard,
    LoginView, 
    LogoutView,
    user_profile,
)

urlpatterns = [
    path('users/', UserListCreateView.as_view(), name='user-list-create'),  # For admin to view and create users
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),  # For admin to update and delete users
    path('users/update-password/<int:pk>/', FirstTimePasswordUpdateView.as_view(), name='update-password'),  # For first-time password updates
    path('password/change/', password_change, name='password-change'),  # Endpoint for changing the password
    path('password/reset/', password_reset, name='password-reset'),  # Endpoint for requesting password reset
    path('dashboard/', dashboard, name='dashboard'),  # User dashboard
    path('login/', auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),  # User logout
    path('profile/', user_profile, name='user-profile'),  # User profile information
]
