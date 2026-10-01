"""Django settings for running an unmodified Healthchecks image with OIDC support.

This file is part of the OIDC add-on (see docker/oidc/README.md), where it is
installed as hc_oidc.settings, inside a copy of the hc/oidc package.

To use it, set these environment variables for the Healthchecks container:

    PYTHONPATH=/opt/oidc
    DJANGO_SETTINGS_MODULE=hc_oidc.settings

If OIDC_PROVIDER_URL is not set, the resulting settings are identical to the
regular Healthchecks settings.

"""

from __future__ import annotations

from typing import Any

from hc.settings import *  # noqa: F403

from .conf import APP, configure_oidc

if configure_oidc(globals()):
    # The unmodified hc/urls.py does not know about OIDC,
    # so use the URL patterns provided by this module instead
    ROOT_URLCONF = __name__


def __getattr__(name: str) -> Any:
    # Build the URL patterns lazily: this module is imported while the settings
    # are being loaded, but views can only be imported once Django is set up
    if name != "urlpatterns":
        raise AttributeError(name)

    from django.core.exceptions import ImproperlyConfigured
    from django.urls import include, path

    try:
        # These rely on Healthchecks internals, which a newer upstream
        # version may have changed
        from hc.urls import prefix

        from . import views
    except ImportError as e:
        msg = f"The OIDC add-on is incompatible with this Healthchecks version: {e}"
        raise ImproperlyConfigured(msg) from e

    return [
        # Handles OIDC_AUTO_LOGIN, the unmodified login view does not
        path(f"{prefix}accounts/login/", views.login),
        path(prefix, include(f"{APP}.urls")),
        path("", include("hc.urls")),
    ]
