from rest_framework import permissions

class IsClientOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow clients and admins to access the lease views.
    """

    def has_permission(self, request, view):
        # Check if the user is authenticated
        if request.user and request.user.is_authenticated:
            # Allow access if the user is a client or admin
            return request.user.user_type in ['client', 'admin']
        return False
