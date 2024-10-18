# bnbu_backend_api/account/urls.py
from django.urls import path
from .views import (dashboard, register, login_view,profile, CustomPasswordResetView,CustomPasswordResetConfirmView, CustomLogoutView,
)

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('register/', register, name='register'),
    path('login/', login_view, name='login'),
    path('profile/', profile, name='profile'),
    
]


# bnbu_backend_api/account/urls.py
from django.urls import path
from .views import dashboard, register, login_view, profile
from .views import UserListCreateView, UserDetailView, user_profile

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('register/', register, name='register'),
    path('login/', login_view, name='login'),
    path('profile/', profile, name='profile'),
    path('password_reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('reset/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('logout/', CustomLogoutView.as_view(next_page='login'), name='logout'),
    
    # API URLs
    path('api/users/', UserListCreateView.as_view(), name='user-list-create'),
    path('api/users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('api/profile/', user_profile, name='user-profile'),
]
