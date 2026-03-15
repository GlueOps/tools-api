GO_IMAGE := golang:1.24-alpine@sha256:8bee1901f1e530bfb4a7850aa7a479d17ae3a18beb6e09064ed54cfd245b7191
MODULE := github.com/GlueOps/tools-api/cli
VERSION ?= dev
COMMIT_SHA ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
SHORT_SHA ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_TIMESTAMP ?= $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_REF ?= $(shell git describe --tags --always 2>/dev/null || echo unknown)

LDFLAGS := -s -w \
	-X $(MODULE)/internal/version.Version=$(VERSION) \
	-X $(MODULE)/internal/version.CommitSHA=$(COMMIT_SHA) \
	-X $(MODULE)/internal/version.ShortSHA=$(SHORT_SHA) \
	-X $(MODULE)/internal/version.BuildTimestamp=$(BUILD_TIMESTAMP) \
	-X $(MODULE)/internal/version.GitRef=$(GIT_REF)

.PHONY: build build-all clean

# Build for current platform
build:
	docker run --rm -v "$$(pwd):/app" -w /app \
		-e CGO_ENABLED=0 \
		$(GO_IMAGE) go build -ldflags '$(LDFLAGS)' -o tools .

# Build for all release platforms
build-all:
	@for platform in linux/amd64 linux/arm64 darwin/amd64 darwin/arm64; do \
		os=$${platform%/*}; arch=$${platform#*/}; \
		echo "Building tools-$$os-$$arch..."; \
		docker run --rm -v "$$(pwd):/app" -w /app \
			-e CGO_ENABLED=0 -e GOOS=$$os -e GOARCH=$$arch \
			$(GO_IMAGE) go build -ldflags '$(LDFLAGS)' -o "tools-$$os-$$arch" .; \
	done

clean:
	rm -f tools tools-linux-amd64 tools-linux-arm64 tools-darwin-amd64 tools-darwin-arm64
