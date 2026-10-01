from __future__ import annotations

import importlib.util
from typing import Any
from unittest import skipIf
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import include, path

from hc.accounts import oidc_settings
from hc.accounts.oidc_settings import configure_oidc, oidc_check
from hc.settings import envbool, envint, envsecret
from hc.test import BaseTestCase

NO_OIDC = importlib.util.find_spec("mozilla_django_oidc") is None

# Mimic hc/urls.py with OIDC enabled
urlpatterns = [] if NO_OIDC else [path("", include("hc.accounts.oidc"))]
urlpatterns.append(path("", include("hc.urls")))

OIDC_SETTINGS = {
    "ROOT_URLCONF": "hc.accounts.tests.test_oidc",
    "OIDC_PROVIDER_URL": "https://login.example.org",
    "OIDC_RP_CLIENT_ID": "client-id",
    "OIDC_RP_CLIENT_SECRET": "client-secret",
    "OIDC_RP_SIGN_ALGO": "RS256",
    "OIDC_RP_SCOPES": "openid email",
    "OIDC_OP_AUTHORIZATION_ENDPOINT": "https://login.example.org/auth",
    "OIDC_OP_TOKEN_ENDPOINT": "https://login.example.org/token",
    "OIDC_OP_USER_ENDPOINT": "https://login.example.org/userinfo",
    "OIDC_OP_JWKS_ENDPOINT": "https://login.example.org/jwks",
    "OIDC_CREATE_USER": True,
    "OIDC_AUTO_LOGIN": False,
}


class OidcDisabledTestCase(BaseTestCase):
    def test_it_does_not_show_sso_button(self) -> None:
        r = self.client.get("/accounts/login/")
        self.assertNotContains(r, "Single Sign-On")

    def test_oidc_urls_are_not_registered(self) -> None:
        r = self.client.get("/oidc/authenticate/")
        self.assertEqual(r.status_code, 404)


@skipIf(NO_OIDC, "mozilla-django-oidc is not installed")
@override_settings(**OIDC_SETTINGS)
class OidcLoginTestCase(BaseTestCase):
    def test_it_shows_sso_button(self) -> None:
        r = self.client.get("/accounts/login/")
        self.assertContains(r, "Log In with Single Sign-On")
        self.assertContains(r, 'href="/oidc/authenticate/"')
        self.assertNotContains(r, "Single sign-on failed")

    def test_it_passes_next_to_sso_button(self) -> None:
        url = f"/projects/{self.project.code}/checks/"
        r = self.client.get(f"/accounts/login/?next={url}")
        self.assertContains(r, f"/oidc/authenticate/?next=%2Fprojects%2F")

    def test_it_ignores_bad_next(self) -> None:
        r = self.client.get("/accounts/login/?next=https://evil.example.org/")
        self.assertContains(r, 'href="/oidc/authenticate/"')
        self.assertNotContains(r, "evil")

    def test_it_shows_failure_message(self) -> None:
        r = self.client.get("/accounts/login/?oidc_failed")
        self.assertContains(r, "Single sign-on failed")

    @override_settings(OIDC_AUTO_LOGIN=True)
    def test_it_redirects_to_sso(self) -> None:
        r = self.client.get("/accounts/login/")
        self.assertRedirects(r, "/oidc/authenticate/", fetch_redirect_response=False)

    @override_settings(OIDC_AUTO_LOGIN=True)
    def test_auto_login_does_not_loop_after_failure(self) -> None:
        r = self.client.get("/accounts/login/?oidc_failed")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Single sign-on failed")

    def _login_view(self, url: str) -> HttpResponse:
        # Calls the login view used by docker/oidc/local_settings.py
        from hc.accounts import oidc

        request = RequestFactory().get(url)
        request.user = AnonymousUser()
        request.session = SessionStore()
        return oidc.login(request)

    @override_settings(OIDC_AUTO_LOGIN=True)
    def test_upstream_login_view_redirects_to_sso(self) -> None:
        r = self._login_view("/accounts/login/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/oidc/authenticate/")

    @override_settings(OIDC_AUTO_LOGIN=True)
    def test_upstream_login_view_falls_back_after_failure(self) -> None:
        r = self._login_view("/accounts/login/?oidc_failed")
        self.assertEqual(r.status_code, 200)

    def test_upstream_login_view_shows_login_page(self) -> None:
        r = self._login_view("/accounts/login/")
        self.assertEqual(r.status_code, 200)

    def test_authenticate_redirects_to_provider(self) -> None:
        r = self.client.get("/oidc/authenticate/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://login.example.org/auth?"))
        self.assertIn("client_id=client-id", r["Location"])


@skipIf(NO_OIDC, "mozilla-django-oidc is not installed")
@override_settings(**OIDC_SETTINGS)
class OidcBackendTestCase(BaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        from hc.accounts.oidc import OIDCBackend

        self.backend = OIDCBackend()

    def test_it_matches_existing_user_by_email(self) -> None:
        users = self.backend.filter_users_by_claims({"email": "ALICE@example.org"})
        self.assertEqual(list(users), [self.alice])

    def test_it_creates_user(self) -> None:
        user = self.backend.create_user({"email": "Dave@example.org"})
        self.assertEqual(user.email, "dave@example.org")
        self.assertTrue(User.objects.filter(email="dave@example.org").exists())
        # It should also create a profile and a project
        self.assertTrue(user.profile)
        self.assertEqual(user.project_set.count(), 1)

    def test_it_rejects_unverified_email(self) -> None:
        claims = {"email": "alice@example.org", "email_verified": False}
        self.assertFalse(self.backend.verify_claims(claims))

    @override_settings(OIDC_ALLOW_UNVERIFIED_EMAIL=True)
    def test_it_allows_unverified_email_if_configured(self) -> None:
        claims = {"email": "alice@example.org", "email_verified": False}
        self.assertTrue(self.backend.verify_claims(claims))

    def test_it_accepts_verified_email(self) -> None:
        claims = {"email": "alice@example.org", "email_verified": True}
        self.assertTrue(self.backend.verify_claims(claims))

    def test_it_accepts_missing_email_verified_claim(self) -> None:
        self.assertTrue(self.backend.verify_claims({"email": "alice@example.org"}))

    def test_it_requires_email(self) -> None:
        self.assertFalse(self.backend.verify_claims({"sub": "123"}))


@override_settings(
    OIDC_PROVIDER_URL="https://login.example.org",
    OIDC_RP_CLIENT_ID="client-id",
    OIDC_RP_CLIENT_SECRET="client-secret",
    OIDC_RP_SCOPES="openid email",
)
class OidcSystemCheckTestCase(BaseTestCase):
    def test_it_accepts_complete_configuration(self) -> None:
        self.assertEqual(oidc_check(), [])

    @override_settings(OIDC_PROVIDER_URL="")
    def test_it_does_nothing_when_disabled(self) -> None:
        self.assertEqual(oidc_check(), [])

    @override_settings(OIDC_RP_CLIENT_ID=None)
    def test_it_warns_about_missing_client_id(self) -> None:
        ids = [item.id for item in oidc_check()]
        self.assertEqual(ids, ["hc.accounts.W001"])

    @override_settings(OIDC_RP_CLIENT_SECRET="")
    def test_it_warns_about_missing_client_secret(self) -> None:
        ids = [item.id for item in oidc_check()]
        self.assertEqual(ids, ["hc.accounts.W002"])

    @override_settings(OIDC_RP_SCOPES="openid profile")
    def test_it_warns_about_missing_email_scope(self) -> None:
        ids = [item.id for item in oidc_check()]
        self.assertEqual(ids, ["hc.accounts.W003"])


ENV = {
    "OIDC_PROVIDER_URL": "https://login.example.org/",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "OIDC_OP_AUTHORIZATION_ENDPOINT": "https://login.example.org/auth",
    "OIDC_OP_TOKEN_ENDPOINT": "https://login.example.org/token",
    "OIDC_OP_USER_ENDPOINT": "https://login.example.org/userinfo",
    "OIDC_OP_JWKS_ENDPOINT": "https://login.example.org/jwks",
}


class ConfigureOidcTestCase(BaseTestCase):
    def _ns(self) -> dict[str, Any]:
        return {
            "envbool": envbool,
            "envint": envint,
            "envsecret": envsecret,
            "SITE_ROOT": "https://hc.example.org/sub",
            "LOGIN_URL": "/sub/accounts/login/",
            "INSTALLED_APPS": ("hc.accounts",),
            "AUTHENTICATION_BACKENDS": ["hc.accounts.backends.EmailBackend"],
            "MIDDLEWARE": ["django.contrib.auth.middleware.AuthenticationMiddleware"],
        }

    def test_backend_path_follows_package_name(self) -> None:
        self.assertEqual(oidc_settings.BACKEND, "hc.accounts.oidc.OIDCBackend")

    @patch.dict("os.environ", {"OIDC_PROVIDER_URL": ""})
    def test_it_does_nothing_without_provider_url(self) -> None:
        ns = self._ns()
        self.assertFalse(configure_oidc(ns))
        self.assertNotIn("OIDC_PROVIDER_URL", ns)

    @skipIf(NO_OIDC, "mozilla-django-oidc is not installed")
    @patch.dict("os.environ", ENV)
    def test_it_configures_oidc(self) -> None:
        ns = self._ns()
        self.assertTrue(configure_oidc(ns))
        self.assertEqual(ns["OIDC_PROVIDER_URL"], "https://login.example.org")
        self.assertEqual(ns["OIDC_RP_CLIENT_ID"], "client-id")
        self.assertEqual(ns["OIDC_OP_TOKEN_ENDPOINT"], "https://login.example.org/token")
        self.assertEqual(ns["LOGIN_REDIRECT_URL"], "/sub/")
        self.assertEqual(ns["LOGIN_REDIRECT_URL_FAILURE"], "/sub/accounts/login/?oidc_failed")
        self.assertIn("mozilla_django_oidc", ns["INSTALLED_APPS"])
        self.assertIn(oidc_settings.BACKEND, ns["AUTHENTICATION_BACKENDS"])

        # A second call (e.g., the add-on settings on top of hc/settings.py)
        # must not configure OIDC twice
        self.assertFalse(configure_oidc(ns))
        self.assertEqual(ns["AUTHENTICATION_BACKENDS"].count(oidc_settings.BACKEND), 1)

    @patch.dict("os.environ", ENV)
    def test_it_reports_missing_packages(self) -> None:
        with patch.object(oidc_settings, "find_spec", lambda name: None):
            with self.assertRaisesRegex(ImproperlyConfigured, "requests"):
                configure_oidc(self._ns())
