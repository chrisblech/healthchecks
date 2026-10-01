"""Authentication backend for the optional OpenID Connect support.

This module imports mozilla_django_oidc, so it must not be imported
unless the OIDC feature is enabled.

"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import QuerySet
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from hc.accounts.views import _make_user

from .models import OIDCIdentity

# A fixed name (instead of __name__, which is hc.oidc.auth or hc_oidc.auth): the
# messages then end up in the container log in both setups, like the messages
# of mozilla-django-oidc itself, and not in Healthchecks' "hc" logger
logger = logging.getLogger("hc_oidc")


class OIDCBackend(OIDCAuthenticationBackend):  # type: ignore[misc]
    """Match users by their OIDC identity (the "sub" claim).

    On the first OIDC login, an existing account with a matching email address
    gets linked to the OIDC identity (unless OIDC_LINK_BY_EMAIL is False).
    From then on, only the OIDC identity counts: a linked account cannot be
    taken over by another identity that claims the same email address.

    """

    def verify_claims(self, claims: dict[str, Any]) -> bool:
        # Unless OIDC_ALLOW_UNVERIFIED_EMAIL is set, do not match or create
        # accounts based on email addresses the identity provider has
        # explicitly marked as unverified
        allow_unverified = getattr(settings, "OIDC_ALLOW_UNVERIFIED_EMAIL", False)
        if not claims.get("sub"):
            reason = "the 'sub' claim is missing"
        elif not claims.get("email"):
            reason = (
                "the 'email' claim is missing (does the identity provider allow "
                "the 'email' scope for this client, and does the user have an "
                "email address?)"
            )
        elif claims.get("email_verified") is False and not allow_unverified:
            reason = (
                "the identity provider reports the email address as unverified "
                "(see OIDC_ALLOW_UNVERIFIED_EMAIL)"
            )
        else:
            return True

        # Log the claim names only, the values are personal data
        logger.warning(
            "OIDC login rejected: %s. Received claims: %s",
            reason,
            ", ".join(sorted(claims)),
        )
        return False

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
        self._update_admin_status(user, claims)
        return user

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        # Links the account if it was matched by email address
        self._link(user, claims)
        self._update_admin_status(user, claims)
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

    def _update_admin_status(self, user: User, claims: dict[str, Any]) -> None:
        """With OIDC_ADMIN_CLAIM, grant or revoke admin rights based on the claim."""
        if (is_admin := is_admin_by_claims(claims)) is None:
            return

        if user.is_staff != is_admin or user.is_superuser != is_admin:
            user.is_staff = user.is_superuser = is_admin
            user.save(update_fields=["is_staff", "is_superuser"])


def is_admin_by_claims(claims: dict[str, Any]) -> bool | None:
    """Evaluate OIDC_ADMIN_CLAIM and OIDC_ADMIN_VALUE.

    Return None if OIDC_ADMIN_CLAIM is not set. Otherwise, look up the claim
    (a dotted name like "realm_access.roles" looks up nested claims) and return:

    * the claim's value, if it is a boolean,
    * whether the claim contains OIDC_ADMIN_VALUE, if it is a list,
    * whether the claim equals OIDC_ADMIN_VALUE, otherwise.

    A missing claim means "not an admin".

    """
    if not (claim := getattr(settings, "OIDC_ADMIN_CLAIM", None)):
        return None

    value: Any = claims
    for key in claim.split("."):
        value = value.get(key) if isinstance(value, dict) else None

    expected = getattr(settings, "OIDC_ADMIN_VALUE", "admin")
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return expected in [str(item) for item in value]
    return value is not None and str(value) == expected
