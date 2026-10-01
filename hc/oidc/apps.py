from __future__ import annotations

from django.apps import AppConfig


class OidcConfig(AppConfig):
    # This package is hc.oidc in this repository, but hc_oidc in the add-on for
    # the upstream image (see docker/oidc/README.md). The fixed label keeps the
    # database tables and migrations identical in both cases.
    name = __name__.rpartition(".")[0]
    label = "hc_oidc"
    verbose_name = "OpenID Connect"
    default_auto_field = "django.db.models.AutoField"
