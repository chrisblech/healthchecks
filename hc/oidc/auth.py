"""Authentication backend for the optional OpenID Connect support.

This module imports mozilla_django_oidc, so it must not be imported
unless the OIDC feature is enabled.

"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import QuerySet
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from hc.accounts.views import _make_user

from .models import OIDCIdentity


class OIDCBackend(OIDCAuthenticationBackend):  # type: ignore[misc]
    """Match users by their OIDC identity (the "sub" claim).

    On the first OIDC login, an existing account with a matching email address
    gets linked to the OIDC identity (unless OIDC_LINK_BY_EMAIL is False).
    From then on, only the OIDC identity counts: a linked account cannot be
    taken over by another identity that claims the same email address.

    """

    def verify_claims(self, claims: dict[str, Any]) -> bool:
        if not claims.get("sub"):
            return False

        # Unless OIDC_ALLOW_UNVERIFIED_EMAIL is set, do not match or create
        # accounts based on email addresses the identity provider has
        # explicitly marked as unverified
        allow_unverified = getattr(settings, "OIDC_ALLOW_UNVERIFIED_EMAIL", False)
        if claims.get("email_verified") is False and not allow_unverified:
            return False

        return bool(super().verify_claims(claims))

    def filter_users_by_claims(self, claims: dict[str, Any]) -> QuerySet[User]:
        issuer = settings.OIDC_PROVIDER_URL
        linked = User.objects.filter(
            oidc_identities__issuer=issuer, oidc_identities__sub=claims["sub"]
        )
        if linked.exists() or not getattr(settings, "OIDC_LINK_BY_EMAIL", True):
            return linked

        # Not linked yet: look for an account with a matching email address
        # that is not already linked to another identity at this provider
        if not (email := claims.get("email")):
            return User.objects.none()
        q = User.objects.filter(email__iexact=email)
        return q.exclude(oidc_identities__issuer=issuer)

    def create_user(self, claims: dict[str, Any]) -> User | None:
        email = claims["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            # An account with this email address exists, but it could not be
            # matched: it is linked to another identity, or OIDC_LINK_BY_EMAIL
            # is False. Do not create a second account with the same address.
            return None

        user = _make_user(email)
        self._link(user, claims)
        return user

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        # Links the account if it was matched by email address
        self._link(user, claims)
        return user

    def get_user(self, user_id: int) -> User | None:
        try:
            return User.objects.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return None

    def _link(self, user: User, claims: dict[str, Any]) -> None:
        OIDCIdentity.objects.get_or_create(
            user=user,
            issuer=settings.OIDC_PROVIDER_URL,
            defaults={"sub": claims["sub"]},
        )
