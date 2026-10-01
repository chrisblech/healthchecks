# OIDC Add-on for the Upstream Docker Image

Images built from this repository support single sign-on via OpenID Connect
out of the box (see
[OIDC_PROVIDER_URL](../../templates/docs/self_hosted_configuration.md#OIDC_PROVIDER_URL)).
This directory provides the same feature as an **add-on for the unmodified upstream
image** (`healthchecks/healthchecks`). It is meant for deployments that:

* want to follow upstream releases by only changing the image tag,
* have no (easy) access to the host filesystem, e.g., stacks managed by Portainer.

## How It Works

The add-on is a small image (`ghcr.io/chrisblech/healthchecks-oidc-addon`) that runs
as a one-shot container. It copies its contents into a named volume and exits:

```
/opt/oidc/                      (named volume, mounted read-only into the app)
├── mozilla_django_oidc/        the mozilla-django-oidc library
└── hc_oidc/                    a copy of the hc/oidc package (without tests)
    ├── settings.py             docker/oidc/settings.py
    └── ...                     backend, views, model and migrations
```

The Healthchecks container mounts the volume and gets two environment variables:

* `PYTHONPATH=/opt/oidc` makes the add-on importable.
* `DJANGO_SETTINGS_MODULE=hc_oidc.settings` selects the add-on's settings module.
  Upstream only sets `hc.settings` as a default, so the environment variable wins.

`hc_oidc.settings` imports all regular settings from `hc.settings`, adds the OIDC
configuration, and routes requests through its own URL patterns (OIDC URLs plus
the unmodified `hc.urls`). No file of the Healthchecks image is modified or
overlaid. `hc_oidc` is the same package the full integration in this repository
uses (`hc/oidc`), so both share code, environment variables and behavior.

`hc_oidc` is also a Django app with its own database table (the links between
user accounts and OIDC identities). The regular `manage.py migrate` run at
container start creates it. The app label is the same in both setups, so you
can switch between the add-on and an image built from this repository without
losing the links.

Consequences:

* **Upstream updates:** change the tag of the Healthchecks image and redeploy.
  The add-on volume is independent of the app image, nothing needs to be
  re-injected, and no access to the Docker socket is needed.
* **Add-on updates:** change the tag of the add-on image and redeploy. The
  add-on container runs before the app container on every deployment
  (`depends_on: condition: service_completed_successfully`), and replaces the
  volume's contents.
* **No OIDC:** without `OIDC_PROVIDER_URL`, the add-on settings are identical
  to the regular settings.

## Setup

See [docker-compose.yml](docker-compose.yml) for a complete example stack. The
relevant parts:

```yaml
services:
  oidc-addon:
    image: ghcr.io/chrisblech/healthchecks-oidc-addon:1.0.0
    volumes:
      - oidc-addon:/target
    restart: "no"

  web:
    image: healthchecks/healthchecks:v4.4
    depends_on:
      oidc-addon:
        condition: service_completed_successfully
    volumes:
      - oidc-addon:/opt/oidc:ro
    environment:
      - PYTHONPATH=/opt/oidc
      - DJANGO_SETTINGS_MODULE=hc_oidc.settings
      - OIDC_PROVIDER_URL=https://login.example.org/
      - OIDC_CLIENT_ID=healthchecks
      - OIDC_CLIENT_SECRET=...

volumes:
  oidc-addon:
```

All `OIDC_*` environment variables are documented in
[self_hosted_configuration.md](../../templates/docs/self_hosted_configuration.md#OIDC_PROVIDER_URL).
In the identity provider, use `SITE_ROOT/oidc/callback/` as the redirect URI.

Differences to the full integration, because upstream templates and views stay
unmodified:

* The login page has no "Log In with Single Sign-On" button. Either set
  `OIDC_AUTO_LOGIN=True` (the login page then redirects to the identity provider),
  or link users to `SITE_ROOT/oidc/authenticate/`.
* After a failed single sign-on, the regular login page is shown without an
  error message.

## Building and Publishing the Add-on Image

The GitHub workflow [publish_oidc_addon.yml](../../.github/workflows/publish_oidc_addon.yml)
builds the image and pushes it to the GitHub Container Registry:

* every push to the `feature/oidc` branch that touches the add-on publishes the
  `feature-oidc` and `sha-<commit>` tags,
* pushing a git tag `oidc-addon-vX.Y.Z` publishes the `X.Y.Z` and `latest` tags.

New GHCR packages are private. Either make the package public (GitHub → Packages →
healthchecks-oidc-addon → Package settings), or add the registry with a token to
Portainer.

To build the image manually, run this from the repository root:

```bash
docker build -f docker/oidc/Dockerfile -t healthchecks-oidc-addon .
```

## Compatibility with Upstream Updates

The add-on relies on a few Healthchecks internals: `hc.settings` (including the
`envbool`, `envint`, `envsecret` helpers), `hc.urls.prefix`, and
`_make_user`, `_allow_redirect` and `login` in `hc.accounts.views`. It also expects
the Healthchecks image to provide `requests`, `PyJWT` and `cryptography`, which
`mozilla-django-oidc` depends on.

If a new upstream version breaks any of this, Healthchecks refuses to start
(`manage.py migrate` fails before uWSGI serves requests), with an error message
that names the problem. Recommended practice:

* pin both image tags (no `latest` in production),
* try a new upstream tag in a test instance before updating production.
