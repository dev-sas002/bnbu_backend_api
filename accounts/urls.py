# bnbu_backend_api/account/urls.py
from django.urls import path
from .views import (dashboard, register, login_view,profile, CustomPasswordResetView,CustomPasswordResetConfirmView, CustomLogoutView,
)

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('register/', register, name='register'),
    path('login/', login_view, name='login'),
    path('profile/', profile, name='profile'),
    path('password_reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('reset/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('logout/', CustomLogoutView.as_view(next_page='login'), name='logout'),  # Add your logout route here
]
