"""Optional OpenID Connect support, used only when OIDC_PROVIDER_URL is set.

This module imports mozilla_django_oidc, so it must not be imported
unless the OIDC feature is enabled.

"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from hc.accounts.views import _make_user


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
