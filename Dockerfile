FROM python:3.14-slim

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

RUN pip install --no-cache-dir pipenv

COPY Pipfile Pipfile.lock ./
RUN pipenv install --system

COPY app/ /code/app

CMD ["fastapi", "run"]
