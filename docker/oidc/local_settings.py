"""Add OpenID Connect single sign-on to an unmodified Healthchecks image.

Mount this file as /opt/healthchecks/hc/local_settings.py. It reuses the OIDC
code from this repository, which must be mounted alongside it:

  hc/accounts/oidc.py           -> /opt/healthchecks/hc/accounts/oidc.py
  hc/accounts/oidc_settings.py  -> /opt/healthchecks/hc/accounts/oidc_settings.py

See docker/oidc/README.md for details. In an image built from this repository,
OIDC is already configured by hc/settings.py, and this file does nothing.

"""

from __future__ import annotations

import sys
from typing import Any

from hc.accounts.oidc_settings import configure_oidc

# hc/settings.py imports this module at its very end, so the regular settings
# are available (and can be modified) via the partially imported settings module
_settings = vars(sys.modules["hc.settings"])

if configure_oidc(_settings):
    # The unmodified hc/urls.py does not know about OIDC,
    # so use the URL patterns provided by this module instead
    _settings["ROOT_URLCONF"] = __name__


def __getattr__(name: str) -> Any:
    # Build the URL patterns lazily: this module is imported while the settings
    # are being loaded, but views can only be imported once Django is set up
    if name != "urlpatterns":
        raise AttributeError(name)

    from django.urls import include, path

    from hc.accounts import oidc
    from hc.urls import prefix

    return [
        # Handles OIDC_AUTO_LOGIN, the unmodified login view does not
        path(f"{prefix}accounts/login/", oidc.login),
        path(prefix, include("hc.accounts.oidc")),
        path("", include("hc.urls")),
    ]
