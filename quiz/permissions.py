from rest_framework import permissions

class IsOwner(permissions.BasePermission):
    """
    Object-level permission to only allow owners of a quiz to access/modify it.
    Assumes the model instance has an `owner` attribute.
    """
    def has_object_permission(self, request, view, obj):
        return getattr(obj, 'owner_id', None) == getattr(request.user, 'id', None)
