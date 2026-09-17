"""Staff session login for the operator UI."""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from api.permissions import IsStaffUser


def _user_payload(user) -> dict:
    return {
        "id": user.pk,
        "username": user.get_username(),
        "is_staff": user.is_staff,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request: Request) -> Response:
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def login_view(request: Request) -> Response:
    username = str(request.data.get("username") or "").strip()
    password = str(request.data.get("password") or "")
    if not username or not password:
        return Response(
            {"detail": "Enter your username and password."},
            status=HTTP_400_BAD_REQUEST,
        )
    user = authenticate(request._request, username=username, password=password)
    if user is None:
        return Response(
            {"detail": "That username or password is not right."},
            status=HTTP_401_UNAUTHORIZED,
        )
    if not user.is_staff:
        return Response(
            {"detail": "This sign-in is for operators only."},
            status=HTTP_403_FORBIDDEN,
        )
    login(request._request, user)
    return Response(_user_payload(user))


@api_view(["POST"])
@permission_classes([IsStaffUser])
def logout_view(request: Request) -> Response:
    logout(request._request)
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsStaffUser])
def me(request: Request) -> Response:
    return Response(_user_payload(request.user))
