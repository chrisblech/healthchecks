from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from hc.accounts import views as accounts_views


def login_url(request: HttpRequest) -> str:
    """Return the URL that starts the OIDC login, preserving a safe ?next=."""
    url = reverse("oidc_authentication_init")
    redirect_url = request.GET.get("next")
    if redirect_url and accounts_views._allow_redirect(redirect_url):
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

    Used by docker/oidc/settings.py, where hc.accounts.views.login does
    not know about OIDC.

    """
    return auto_login(request) or accounts_views.login(request)
