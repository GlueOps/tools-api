# Build stage
FROM golang:1.24-alpine AS builder

ARG VERSION=UNKNOWN
ARG COMMIT_SHA=UNKNOWN
ARG SHORT_SHA=UNKNOWN
ARG BUILD_TIMESTAMP=UNKNOWN
ARG GIT_REF=UNKNOWN

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build \
    -ldflags="-s -w \
      -X github.com/GlueOps/tools-api/internal/version.Version=${VERSION} \
      -X github.com/GlueOps/tools-api/internal/version.CommitSHA=${COMMIT_SHA} \
      -X github.com/GlueOps/tools-api/internal/version.ShortSHA=${SHORT_SHA} \
      -X github.com/GlueOps/tools-api/internal/version.BuildTimestamp=${BUILD_TIMESTAMP} \
      -X github.com/GlueOps/tools-api/internal/version.GitRef=${GIT_REF}" \
    -o /server ./cmd/server

# Runtime stage
FROM alpine:3.21
RUN apk add --no-cache ca-certificates
COPY --from=builder /server /server
EXPOSE 8000
ENTRYPOINT ["/server"]
