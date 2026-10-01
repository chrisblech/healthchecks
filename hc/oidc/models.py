from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now


class OIDCIdentity(models.Model):
    """Links a user account to an identity (the "sub" claim) at an OIDC provider."""

    user = models.ForeignKey(User, models.CASCADE, related_name="oidc_identities")
    # The OIDC_PROVIDER_URL value at the time of linking
    issuer = models.CharField(max_length=200)
    sub = models.CharField(max_length=255)
    created = models.DateTimeField(default=now)

    class Meta:
        verbose_name = "OIDC identity"
        verbose_name_plural = "OIDC identities"
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "sub"], name="hc_oidc_unique_issuer_sub"
            ),
            models.UniqueConstraint(
                fields=["user", "issuer"], name="hc_oidc_unique_user_issuer"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sub} @ {self.issuer}"
