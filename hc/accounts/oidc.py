"""Optional OpenID Connect support, used only when OIDC_PROVIDER_URL is set.

This module imports mozilla_django_oidc, so it must not be imported
unless the OIDC feature is enabled.

"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import include, path, reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from hc.accounts import views as accounts_views
from hc.accounts.views import _allow_redirect, _make_user

urlpatterns = [path("oidc/", include("mozilla_django_oidc.urls"))]


class OIDCBackend(OIDCAuthenticationBackend):  # type: ignore[misc]
    def verify_claims(self, claims: dict[str, Any]) -> bool:
        # Unless OIDC_ALLOW_UNVERIFIED_EMAIL is set, do not match or create
        # accounts based on email addresses the identity provider has
        # explicitly marked as unverified
        allow_unverified = getattr(settings, "OIDC_ALLOW_UNVERIFIED_EMAIL", False)
        if claims.get("email_verified") is False and not allow_unverified:
            return False

        return bool(super().verify_claims(claims))

    def create_user(self, claims: dict[str, Any]) -> User:
        return _make_user(claims["email"].lower())

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        return user

    def get_user(self, user_id: int) -> User | None:
        try:
            return User.objects.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return None


def login_url(request: HttpRequest) -> str:
    """Return the URL that starts the OIDC login, preserving a safe ?next=."""
    url = reverse("oidc_authentication_init")
    redirect_url = request.GET.get("next")
    if redirect_url and _allow_redirect(redirect_url):
        url += "?" + urlencode({"next": redirect_url})
    return url


def auto_login(request: HttpRequest) -> HttpResponse | None:
    """With OIDC_AUTO_LOGIN, return a redirect to the identity provider.

    Return None if the regular login page should be shown instead, for example,
    because the previous OIDC login attempt failed.

    """
    if not getattr(settings, "OIDC_AUTO_LOGIN", False):
        return None
    if request.method != "GET" or request.user.is_authenticated:
        return None
    if "oidc_failed" in request.GET:
        return None
    return redirect(login_url(request))


def login(request: HttpRequest) -> HttpResponse:
    """Login view with OIDC_AUTO_LOGIN support for unmodified Healthchecks code.

    Used by docker/oidc/local_settings.py, where hc.accounts.views.login does
    not know about OIDC.

    """
    return auto_login(request) or accounts_views.login(request)
