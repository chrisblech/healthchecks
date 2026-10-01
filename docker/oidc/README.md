# OpenID Connect for the Upstream Docker Image

Images built from this repository support single sign-on via OpenID Connect
out of the box (see
[OIDC_PROVIDER_URL](../../templates/docs/self_hosted_configuration.md#OIDC_PROVIDER_URL)).
This directory shows how to add the same feature to an **unmodified upstream image**
(`healthchecks/healthchecks`) without rebuilding it.

The upstream image already contains all dependencies (Django, requests, PyJWT,
cryptography) except `mozilla-django-oidc` itself. Upstream Healthchecks also loads
an optional `hc/local_settings.py`. The files mounted into the container are:

| Source (this repository)       | Target in the container                          |
| ------------------------------ | ------------------------------------------------ |
| `docker/oidc/local_settings.py`| `/opt/healthchecks/hc/local_settings.py`         |
| `hc/accounts/oidc.py`          | `/opt/healthchecks/hc/accounts/oidc.py`          |
| `hc/accounts/oidc_settings.py` | `/opt/healthchecks/hc/accounts/oidc_settings.py` |
| `mozilla_django_oidc/` package | `/opt/healthchecks/mozilla_django_oidc`          |

The two `hc/accounts/oidc*.py` files are the same ones the full integration
uses, so both setups share the same code and environment variables.

## Option A: Mount Everything (No Build)

Fetch the `mozilla-django-oidc` package once. It is pure Python, so the
wheel only needs to be unpacked:

```bash
pip download mozilla-django-oidc==5.0.2 --no-deps -d /tmp/oidc
```

```bash
python -m zipfile -e /tmp/oidc/mozilla_django_oidc-5.0.2-py3-none-any.whl /tmp/oidc/whl
```

Then copy `/tmp/oidc/whl/mozilla_django_oidc` next to your `docker-compose.yml`.

```yaml
services:
  web:
    image: healthchecks/healthchecks:v4.4
    environment:
      - OIDC_PROVIDER_URL=https://login.example.org/
      - OIDC_CLIENT_ID=healthchecks
      - OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc_client_secret
    volumes:
      - ./healthchecks/docker/oidc/local_settings.py:/opt/healthchecks/hc/local_settings.py:ro
      - ./healthchecks/hc/accounts/oidc.py:/opt/healthchecks/hc/accounts/oidc.py:ro
      - ./healthchecks/hc/accounts/oidc_settings.py:/opt/healthchecks/hc/accounts/oidc_settings.py:ro
      - ./mozilla_django_oidc:/opt/healthchecks/mozilla_django_oidc:ro
```

`/opt/healthchecks` is the working directory of uWSGI and `manage.py`, so the
package is importable from there.

## Option B: Thin Derived Image

To avoid managing the package directory, extend the upstream image with
one layer and keep mounting (or `COPY`ing) the three `.py` files as shown above:

```dockerfile
FROM healthchecks/healthchecks:v4.4
USER root
RUN pip install --no-cache mozilla-django-oidc==5.0.2
USER hc
```

## Differences to the Full Integration

All `OIDC_*` environment variables and the startup warnings work the same.
Because the upstream templates and views stay unmodified:

* The login page has no "Log In with Single Sign-On" button. Either set
  `OIDC_AUTO_LOGIN=True` (the login page then redirects to the identity provider),
  or link users to `SITE_ROOT/oidc/authenticate/`.
* After a failed single sign-on, the regular login page is shown without an
  error message.

When upgrading the upstream image, check that the mounted files still work
with the new version: they rely on `hc.accounts.views._make_user`,
`hc.accounts.views._allow_redirect`, `hc.accounts.views.login` and `hc.urls.prefix`.
