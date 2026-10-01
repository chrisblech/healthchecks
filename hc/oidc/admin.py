from __future__ import annotations

from django.contrib import admin

from .models import OIDCIdentity


@admin.register(OIDCIdentity)
class OIDCIdentityAdmin(admin.ModelAdmin[OIDCIdentity]):
    # Deleting an identity here unlinks the account: on the next OIDC login,
    # it will be linked again by email address (if OIDC_LINK_BY_EMAIL is enabled)
    list_display = ("user", "issuer", "sub", "created")
    list_select_related = ("user",)
    search_fields = ("user__email", "sub")
    readonly_fields = ("user", "issuer", "sub", "created")
