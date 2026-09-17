from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Operators must be logged in as a staff user."""

    message = "This area is for operators only."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
