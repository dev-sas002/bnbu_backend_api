# bnbu_backend_api/account/views.py
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import PasswordChangeForm
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth.models import update_last_login
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from .serializers import FirstTimePasswordUpdateSerializer, UserSerializer, PasswordChangeSerializer, PasswordResetSerializer
from .models import CustomUser
from django.contrib.auth.hashers import make_password
from rest_framework.pagination import PageNumberPagination
    
class UserListCreateView(APIView):
    permission_classes = [IsAdminUser]
    pagination_class = PageNumberPagination

    def get(self, request):
        paginator = self.pagination_class()
        users = CustomUser.objects.all()
        paginated_users = paginator.paginate_queryset(users, request)
        serializer = UserSerializer(paginated_users, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            user.is_active = True
            # Set a temporary password
            temporary_password = "temporary_password123"
            user.set_password(temporary_password)
            user.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class UserDetailView(RetrieveUpdateDestroyAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def put(self, request, *args, **kwargs):
        response = super().put(request, *args, **kwargs)
        return Response({"message": "User updated successfully"}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        return Response({"message": "User deleted successfully"}, status=status.HTTP_204_NO_CONTENT) 
class FirstTimePasswordUpdateView(RetrieveUpdateAPIView):
    serializer_class = FirstTimePasswordUpdateSerializer  # Use the new serializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        return CustomUser.objects.all()

    def post(self, request, *args, **kwargs):
        user = self.get_object()

        # Ensure the authenticated user can only change their own password
        if request.user != user:
            return Response({"error": "You are not allowed to update this user's password."}, status=status.HTTP_403_FORBIDDEN)

        if not user.is_first_login:
            return Response({"error": "Password update not allowed. This is not your first login."}, status=status.HTTP_403_FORBIDDEN)

        # Use the serializer to validate and save the new password
        serializer = self.get_serializer(user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def password_change(request):
    # Use the PasswordChangeSerializer to validate and save the new password
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({"success": "Password changed successfully"}, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def password_reset(request):
    serializer = PasswordResetSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        user = CustomUser.objects.filter(email=email).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = f"http://example.com/reset/{uid}/{token}/"
            
            # Simulating sending the reset email (shows in console)
            send_mail(
                "Password Reset",
                f"Use this link to reset your password: {reset_link}",
                "from@example.com",
                [email],
            )
            
            return Response({"message": "Password reset email sent", "reset_link": reset_link}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = CustomUser.objects.filter(email=email).first()  # Fetch user by email
        if user and user.check_password(password):  # Check if the password matches
            login(request, user)
            if user.is_first_login and user.user_type != 'admin':
                return Response({"message": "First login, password update required"}, status=status.HTTP_200_OK)
            return Response({"message": "Logged in successfully"}, status=status.HTTP_200_OK)
        return Response({"error": "Invalid email or password"}, status=status.HTTP_400_BAD_REQUEST)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    if request.user.user_type == 'admin':
        users = CustomUser.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    elif request.user.user_type == 'coach':
        return Response({"message": "Welcome to coach dashboard"}, status=status.HTTP_200_OK)
    elif request.user.user_type == 'research':
        return Response({"message": "Welcome to research dashboard"}, status=status.HTTP_200_OK)
    elif request.user.user_type == 'client':
        return Response({"message": "Welcome to client dashboard"}, status=status.HTTP_200_OK)
    else:
        return Response({"message": "Welcome to general dashboard"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)
