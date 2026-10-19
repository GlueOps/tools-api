FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

WORKDIR /code

# Accept build arguments for versioning
ARG VERSION=UNKNOWN
ARG COMMIT_SHA=UNKNOWN
ARG SHORT_SHA=UNKNOWN
ARG BUILD_TIMESTAMP=UNKNOWN
ARG GIT_REF=UNKNOWN

ENV VERSION=${VERSION}
ENV COMMIT_SHA=${COMMIT_SHA}
ENV SHORT_SHA=${SHORT_SHA}
ENV BUILD_TIMESTAMP=${BUILD_TIMESTAMP}
ENV GIT_REF=${GIT_REF}

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

# Tailscale (userspace networking) for reaching Proxmox over the tailnet; see entrypoint.sh
COPY --from=ghcr.io/tailscale/tailscale:v1.104.1@sha256:87c55d6be56ad85b3d8bceca5f87f73de288c609131460dd1be1874c250cc41d \
    /usr/local/bin/tailscale /usr/local/bin/tailscaled /usr/local/bin/

RUN pip install --no-cache-dir pipenv

COPY Pipfile Pipfile.lock ./
RUN pipenv install --system

COPY app/ /code/app
COPY entrypoint.sh /entrypoint.sh

CMD ["/entrypoint.sh"]
