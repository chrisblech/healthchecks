"""Settings and system checks for the optional OpenID Connect support.

This module is used while the settings are being loaded: either from
hc/settings.py, or from docker/oidc/settings.py when adding OIDC support to an
unmodified Healthchecks image (see docker/oidc/README.md). It must therefore not
import anything that requires configured settings or a ready app registry.

It must also not hardcode its own package name: in the add-on for the upstream
image, it is installed as hc_oidc.oidc_settings instead of
hc.accounts.oidc_settings.

"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from importlib.util import find_spec
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from django.core.checks import Warning, register
from django.core.exceptions import ImproperlyConfigured

# The module with the OIDC backend, views and URL patterns, located next to this one
OIDC_MODULE = f"{__package__}.oidc"
BACKEND = f"{OIDC_MODULE}.OIDCBackend"
# Packages mozilla-django-oidc needs, but which we expect the Healthchecks
# image to already provide (the add-on installs it with "pip install --no-deps")
REQUIRED_PACKAGES = ("mozilla_django_oidc", "requests", "jwt", "cryptography")
ENDPOINTS = {
    "OIDC_OP_AUTHORIZATION_ENDPOINT": "authorization_endpoint",
    "OIDC_OP_TOKEN_ENDPOINT": "token_endpoint",
    "OIDC_OP_USER_ENDPOINT": "userinfo_endpoint",
    "OIDC_OP_JWKS_ENDPOINT": "jwks_uri",
}


def _discover(provider_url: str, timeout: int | None) -> dict[str, Any]:
    url = f"{provider_url}/.well-known/openid-configuration"
    try:
        with urlopen(url, timeout=timeout) as response:
            result: dict[str, Any] = json.loads(response.read())
            return result
    except Exception as e:
        msg = f"Error loading OIDC configuration from {url}: {e}"
        raise ImproperlyConfigured(msg) from e


def configure_oidc(ns: dict[str, Any]) -> bool:
    """Add OIDC settings to the settings namespace `ns`.

    `ns` must already contain the regular Healthchecks settings and the
    envbool, envint, envsecret helpers from hc/settings.py.

    Return True if OIDC got configured, and False if OIDC_PROVIDER_URL is not set
    or OIDC was already configured.

    """

    provider_url = os.getenv("OIDC_PROVIDER_URL", "").removesuffix("/")
    if not provider_url or "mozilla_django_oidc" in ns["INSTALLED_APPS"]:
        return False

    if missing := [pkg for pkg in REQUIRED_PACKAGES if find_spec(pkg) is None]:
        msg = f"OIDC_PROVIDER_URL is set, but Python packages are missing: {missing}"
        raise ImproperlyConfigured(msg)

    envbool, envint, envsecret = ns["envbool"], ns["envint"], ns["envsecret"]
    ns["OIDC_PROVIDER_URL"] = provider_url
    ns["OIDC_RP_CLIENT_ID"] = envsecret("OIDC_CLIENT_ID")
    ns["OIDC_RP_CLIENT_SECRET"] = envsecret("OIDC_CLIENT_SECRET")
    ns["OIDC_RP_SIGN_ALGO"] = os.getenv("OIDC_RP_SIGN_ALGO", "RS256")
    ns["OIDC_RP_SCOPES"] = os.getenv("OIDC_RP_SCOPES", "openid email")
    ns["OIDC_TOKEN_USE_BASIC_AUTH"] = envbool("OIDC_TOKEN_USE_BASIC_AUTH", "False")
    ns["OIDC_USE_PKCE"] = envbool("OIDC_USE_PKCE", "False")
    ns["OIDC_CREATE_USER"] = envbool("OIDC_CREATE_USER", "True")
    ns["OIDC_ALLOW_UNVERIFIED_EMAIL"] = envbool("OIDC_ALLOW_UNVERIFIED_EMAIL", "False")
    ns["OIDC_AUTO_LOGIN"] = envbool("OIDC_AUTO_LOGIN", "False")
    ns["OIDC_TIMEOUT"] = envint("OIDC_TIMEOUT", "10")

    # Endpoints can be specified explicitly, any missing ones are looked up
    # via the provider's /.well-known/openid-configuration document
    conf: dict[str, Any] | None = None
    for setting, key in ENDPOINTS.items():
        if not (value := os.getenv(setting)):
            if conf is None:
                conf = _discover(provider_url, ns["OIDC_TIMEOUT"])
            if not (value := conf.get(key)):
                raise ImproperlyConfigured(f"Could not determine {setting}")
        ns[setting] = value

    site_root_path = urlparse(ns["SITE_ROOT"]).path
    ns["LOGIN_REDIRECT_URL"] = f"{site_root_path}/"
    ns["LOGIN_REDIRECT_URL_FAILURE"] = f"{ns['LOGIN_URL']}?oidc_failed"

    ns["INSTALLED_APPS"] = (*ns["INSTALLED_APPS"], "mozilla_django_oidc")
    ns["AUTHENTICATION_BACKENDS"] = [*ns["AUTHENTICATION_BACKENDS"], BACKEND]
    if envbool("OIDC_SESSION_REFRESH", "False"):
        middleware = list(ns["MIDDLEWARE"])
        auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"
        middleware.insert(
            middleware.index(auth_middleware) + 1,
            "mozilla_django_oidc.middleware.SessionRefresh",
        )
        ns["MIDDLEWARE"] = middleware

    return True


@register()
def oidc_check(
    app_configs: Sequence[Any] | None = None,
    databases: Sequence[str] | None = None,
    **kwargs: Any,
) -> list[Warning]:
    """System check: warn about incomplete OIDC configuration (W001, W002, W003).

    The check gets registered when this module is imported, which only
    happens when OIDC_PROVIDER_URL is set.

    """

    from django.conf import settings

    if not getattr(settings, "OIDC_PROVIDER_URL", None):
        return []

    items = []
    hint = "See https://healthchecks.io/docs/self_hosted_configuration/#OIDC_PROVIDER_URL"
    if not getattr(settings, "OIDC_RP_CLIENT_ID", None):
        items.append(
            Warning(
                "OIDC_PROVIDER_URL is set but OIDC_CLIENT_ID is missing",
                hint=hint,
                id="hc.accounts.W001",
            )
        )

    if not getattr(settings, "OIDC_RP_CLIENT_SECRET", None):
        items.append(
            Warning(
                "OIDC_PROVIDER_URL is set but OIDC_CLIENT_SECRET is missing",
                hint=hint,
                id="hc.accounts.W002",
            )
        )

    if "email" not in getattr(settings, "OIDC_RP_SCOPES", "").split():
        items.append(
            Warning(
                "OIDC_RP_SCOPES does not include the 'email' scope",
                hint="Healthchecks needs the user's email address to log them in",
                id="hc.accounts.W003",
            )
        )

    return items
