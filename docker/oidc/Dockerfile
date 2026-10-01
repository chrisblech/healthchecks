# OIDC add-on for the unmodified upstream Healthchecks image, see README.md.
# Build from the repository root:
#
#   docker build -f docker/oidc/Dockerfile -t healthchecks-oidc-addon .
#
# The add-on consists of pure Python code only, so the build stage always runs
# on the build platform, and only the tiny final stage is platform-specific.

FROM --platform=$BUILDPLATFORM python:3.14-slim-trixie AS builder

ARG MOZILLA_DJANGO_OIDC_VERSION=5.0.2

# --no-deps: the dependencies (requests, PyJWT, cryptography) are already part of
# the Healthchecks image. Installing them here would shadow the image's versions.
RUN pip install --no-cache-dir --no-deps --target /addon \
    "mozilla-django-oidc==${MOZILLA_DJANGO_OIDC_VERSION}"

COPY hc/accounts/oidc.py hc/accounts/oidc_settings.py /addon/hc_oidc/
COPY docker/oidc/settings.py /addon/hc_oidc/settings.py

# The add-on volume is mounted read-only, so precompile the bytecode here
RUN touch /addon/hc_oidc/__init__.py && \
    python -m compileall -q /addon && \
    chmod -R a+rX /addon

FROM busybox:stable

COPY --from=builder /addon /addon

# Replace the contents of the volume mounted at /target with this add-on version
CMD ["sh", "-c", "rm -rf /target/* && cp -a /addon/. /target/ && echo 'OIDC add-on installed'"]
