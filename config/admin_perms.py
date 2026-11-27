"""Maxsus admin sahifalari uchun huquq tekshiruvi.

`admin_site.admin_view` faqat is_staff'ni tekshiradi; bu sahifalarda esa shaxsiy ma'lumotlar
(karta, telefon, yozishmalar) va pulga oid amallar bor — model huquqlari talab qilinadi.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied


def require_perms(view_perm, change_perm=None):
    """GET uchun view_perm, POST uchun change_perm (berilmasa — view_perm) kerak."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            perm = change_perm if request.method == 'POST' and change_perm else view_perm
            if not request.user.has_perm(perm):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
