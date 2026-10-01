from __future__ import annotations

from django.test.utils import override_settings

from hc.api.apps import settings_check
from hc.test import BaseTestCase


@override_settings(EMAIL_HOST="localhost", APPRISE_ENABLED=False)
class SystemChecksCase(BaseTestCase):
    @override_settings(SITE_ROOT="example.com")
    def test_it_validates_site_root_syntax(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W001"])

    @override_settings(SITE_ROOT="http://surprise.example.com")
    def test_it_checks_site_root_host_is_present_in_allowed_hosts(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.E002"])

    @override_settings(MAILERS={})
    def test_it_warns_about_missing_smtp_credentials(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W002"])

    @override_settings(SECURE_PROXY_SSL_HEADER="abc")
    def test_it_checks_secure_proxy_ssl_header_tupleness(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W005"])

    @override_settings(APPRISE_ENABLED=True, INTEGRATIONS_ALLOW_PRIVATE_IPS=False)
    def test_it_checks_apprise_and_private_ips(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W006"])

    @override_settings(
        OIDC_PROVIDER_URL="https://login.example.org",
        OIDC_RP_CLIENT_ID="client-id",
        OIDC_RP_CLIENT_SECRET="client-secret",
        OIDC_RP_SCOPES="openid email",
    )
    def test_it_accepts_complete_oidc_configuration(self) -> None:
        self.assertEqual(settings_check(None, None), [])

    @override_settings(
        OIDC_PROVIDER_URL="https://login.example.org",
        OIDC_RP_CLIENT_ID=None,
        OIDC_RP_CLIENT_SECRET="client-secret",
        OIDC_RP_SCOPES="openid email",
    )
    def test_it_warns_about_missing_oidc_client_id(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W007"])

    @override_settings(
        OIDC_PROVIDER_URL="https://login.example.org",
        OIDC_RP_CLIENT_ID="client-id",
        OIDC_RP_CLIENT_SECRET="",
        OIDC_RP_SCOPES="openid email",
    )
    def test_it_warns_about_missing_oidc_client_secret(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W008"])

    @override_settings(
        OIDC_PROVIDER_URL="https://login.example.org",
        OIDC_RP_CLIENT_ID="client-id",
        OIDC_RP_CLIENT_SECRET="client-secret",
        OIDC_RP_SCOPES="openid profile",
    )
    def test_it_warns_about_missing_oidc_email_scope(self) -> None:
        ids = [item.id for item in settings_check(None, None)]
        self.assertEqual(ids, ["hc.api.W009"])
