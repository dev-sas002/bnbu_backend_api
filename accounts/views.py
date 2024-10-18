# bnbu_backend_api/account/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView, LogoutView
from .models import CustomUser
from django.urls import reverse
from .forms import CustomUserCreationForm
from django.contrib import messages

def dashboard(request):
    return render(request, 'accounts/dashboard.html')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])  # Ensure password is hashed
            user.user_type = request.POST.get('user_type')
            user.save()
            login(request, user)
            return redirect('login')
        
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/register.html', {'form': form, 'user_type_choices': CustomUser.NON_ADMIN_USER_TYPE_CHOICES})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)  # Use authenticate
            if user is not None:
                login(request, user)
                return redirect('profile')
            else:
                messages.error(request, "Invalid username or password")
        else:
            messages.error(request, "Invalid login credentials")
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})

def profile(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'accounts/profile.html', {'user': request.user})

class CustomPasswordResetView(PasswordResetView):
    template_name = 'accounts/password_reset.html'

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'

class CustomLogoutView(LogoutView):
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)  # Treat GET request as POST

