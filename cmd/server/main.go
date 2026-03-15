package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/GlueOps/tools-api/internal/version"
	"github.com/GlueOps/tools-api/pkg/handlers"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
)

func main() {
	// Configure structured JSON logging via log/slog.
	level := parseLogLevel(os.Getenv("LOG_LEVEL"))
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level})))

	// Override Huma's default error creator to return our clean ErrorResponse format
	// (risk M3). Stack traces are logged server-side only — never sent to clients.
	huma.NewError = func(status int, msg string, errs ...error) huma.StatusError {
		detail := msg
		if detail == "" {
			detail = http.StatusText(status)
		}
		// Log stack trace server-side for 5xx errors.
		if status >= 500 {
			buf := make([]byte, 4096)
			n := runtime.Stack(buf, false)
			errMsgs := make([]string, 0, len(errs))
			for _, e := range errs {
				errMsgs = append(errMsgs, e.Error())
			}
			slog.Error("server error",
				"status", status,
				"detail", detail,
				"errors", errMsgs,
				"stack", string(buf[:n]),
			)
		} else if len(errs) > 0 {
			// For 4xx, append validation details to the message.
			parts := []string{detail}
			for _, e := range errs {
				parts = append(parts, e.Error())
			}
			detail = strings.Join(parts, ": ")
		}
		return &types.ErrorResponse{
			Status: status,
			Detail: detail,
		}
	}

	router := chi.NewMux()

	// Audit logging middleware: log every request with authenticated user identity.
	router.Use(auditLogMiddleware)

	// Redirect GET / to /docs (excluded from OpenAPI).
	router.Get("/", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/docs", http.StatusTemporaryRedirect)
	})

	// Create Huma API with application metadata.
	// Use a custom config without the SchemaLinkTransformer so responses
	// don't include a "$schema" field (matching Python/FastAPI behavior).
	appVersion := version.Version
	schemaPrefix := "#/components/schemas/"
	registry := huma.NewMapRegistry(schemaPrefix, huma.DefaultSchemaNamer)
	config := huma.Config{
		OpenAPI: &huma.OpenAPI{
			OpenAPI: "3.1.0",
			Info: &huma.Info{
				Title:       "Tools API",
				Version:     appVersion,
				Description: "Various APIs to help you speed up your development and testing.",
			},
			Components: &huma.Components{
				Schemas: registry,
			},
		},
		OpenAPIPath:   "/openapi",
		DocsPath:      "/docs",
		DocsRenderer: func(api huma.API) http.Handler {
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "text/html")
				w.Write([]byte(`<!DOCTYPE html>
<html>
<head>
  <title>` + api.OpenAPI().Info.Title + `</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: '/openapi',
      dom_id: '#swagger-ui',
      defaultModelsExpandDepth: -1
    });
  </script>
</body>
</html>`))
			})
		},
		SchemasPath:   "/schemas",
		Formats:       huma.DefaultFormats,
		DefaultFormat: "application/json",
	}

	api := humachi.New(router, config)

	// Health endpoint registered directly on chi (excluded from OpenAPI schema).
	router.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy"}`))
	})

	// Register version endpoint.
	huma.Register(api, huma.Operation{
		OperationID: "get-version",
		Method:      http.MethodGet,
		Path:        "/version",
		Summary:     "Contains version information about this tools-api",
	}, handlers.GetVersion)

	// Register storage buckets endpoint (ticket 04).
	huma.Register(api, huma.Operation{
		OperationID: "create-storage-buckets",
		Method:      http.MethodPost,
		Path:        "/v1/storage/buckets",
		Summary:     "Create/Re-create storage buckets that can be used for V2 of our monitoring stack that is Otel based",
		Description: "Note: this can be a DESTRUCTIVE operation. For the provided captain_domain, this will DELETE and then create new/empty storage buckets for loki, tempo, and thanos.",
		Responses: map[string]*huma.Response{
			"200": {Description: "Storage configuration", Content: map[string]*huma.MediaType{"text/plain": {Schema: &huma.Schema{Type: "string"}}}},
		},
	}, handlers.CreateStorageBuckets)

	// Register AWS credentials endpoint (ticket 07).
	huma.Register(api, huma.Operation{
		OperationID: "create-aws-credentials",
		Method:      http.MethodPost,
		Path:        "/v1/aws/credentials",
		Summary:     "Whether it's to create an EKS cluster or to test other things out in an isolated AWS account. These creds will give you Admin level access to the requested account.",
		Description: "If you are testing in AWS/EKS you will need an AWS account to test with. This request will provide you with admin level credentials to the sub account you specify.\nThis can also be used to just get Admin access to a desired sub account.",
		Responses: map[string]*huma.Response{
			"200": {Description: "AWS credentials", Content: map[string]*huma.MediaType{"text/plain": {Schema: &huma.Schema{Type: "string"}}}},
		},
	}, handlers.CreateAwsCredentials)

	// Register GitHub workflow dispatch endpoints (ticket 05).
	huma.Register(api, huma.Operation{
		OperationID: "nuke-aws-account",
		Method:      http.MethodPost,
		Path:        "/v1/aws/nuke",
		Summary:     "Run this after you are done testing within AWS. This will clean up orphaned resources. Note: you may have to run this 2x.",
		Description: "Submit the AWS account name you want to nuke (e.g. glueops-captain-foobar)",
	}, handlers.NukeAwsAccount)

	huma.Register(api, huma.Operation{
		OperationID: "nuke-captain-domain-data",
		Method:      http.MethodPost,
		Path:        "/v1/nuke/domain-data",
		Summary:     "Deletes all backups/data for a provided captain_domain. Running this before a cluster creation helps ensure a clean environment.",
		Description: "Submit the captain_domain/tenant you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will delete all backups and data for the provided captain_domain.\n\nThis will remove things like the vault and cert-manager backups.\n\nNote: this may not delete things like Loki/Thanos/Tempo data as that may be managed outside of AWS.",
	}, handlers.NukeCaptainDomainData)

	huma.Register(api, huma.Operation{
		OperationID: "reset-github-organization",
		Method:      http.MethodPost,
		Path:        "/v1/github/reset-org",
		Summary:     "Resets the GitHub Organization to make it easier to get a new dev cluster runner for Dev",
		Description: "Submit the dev captain_domain you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will reset the GitHub organization so that you can easily get up and running with a new dev cluster.\n\nThis will reset your deployment-configurations repository, it'll bring over a working regcred, and application repos with working github actions so that you can quickly work on the GlueOps stack.\n\nWARNING: By default delete_all_existing_repos = True. Please set it to False or make a manual backup if you are concerned about any data loss within your tenant org (e.g. github.com/development-tenant-*)",
	}, handlers.ResetGitHubOrganization)

	huma.Register(api, huma.Operation{
		OperationID: "get-workflow-run-status",
		Method:      http.MethodGet,
		Path:        "/v1/github/workflow-status",
		Summary:     "Get the status of a GitHub Actions workflow run",
		Description: "Provide a GitHub Actions run URL (e.g. https://github.com/owner/repo/actions/runs/12345678) and get the current status of that workflow run.\nWorks for any repo the configured GITHUB_TOKEN has read access to.",
	}, handlers.GetWorkflowRunStatus)

	// Register chisel endpoints (ticket 06).
	huma.Register(api, huma.Operation{
		OperationID: "create-chisel-nodes",
		Method:      http.MethodPost,
		Path:        "/v1/chisel",
		Summary:     "Creates Chisel nodes for dev/k3d clusters. This allows us to mimic a Cloud Controller for Loadbalancers (e.g. NLBs with EKS)",
		Description: "If you are testing within k3ds you will need chisel to provide you with load balancers.\nFor a provided captain_domain this will delete any existing chisel nodes and provision new ones.\nNote: this will generally result in new IPs being provisioned.",
		Responses: map[string]*huma.Response{
			"200": {Description: "Chisel YAML manifest", Content: map[string]*huma.MediaType{"text/plain": {Schema: &huma.Schema{Type: "string"}}}},
		},
	}, handlers.CreateChiselNodes)

	huma.Register(api, huma.Operation{
		OperationID: "delete-chisel-nodes",
		Method:      http.MethodPost,
		Path:        "/v1/chisel/delete",
		Summary:     "Deletes your chisel nodes. Please run this when you are done with development to save on costs.",
		Description: "When you are done testing with k3ds this will delete your chisel nodes and save on costs.",
	}, handlers.DeleteChiselNodes)

	// Register opsgenie manifest endpoint (ticket 08).
	huma.Register(api, huma.Operation{
		OperationID: "create-opsgenie-manifest",
		Method:      http.MethodPost,
		Path:        "/v1/opsgenie/manifest",
		Summary:     "Creates Opsgenie Alerts Manifest",
		Description: "Create a opsgenie/alertmanager configuration. Do this for any clusters you want alerts on.",
		Responses: map[string]*huma.Response{
			"200": {Description: "Opsgenie manifest", Content: map[string]*huma.MediaType{"text/plain": {Schema: &huma.Schema{Type: "string"}}}},
		},
	}, handlers.CreateOpsgenieManifest)

	// Register captain manifests endpoint (ticket 10).
	huma.Register(api, huma.Operation{
		OperationID: "create-captain-manifests",
		Method:      http.MethodPost,
		Path:        "/v1/captain/manifests",
		Summary:     "Generate captain manifests",
		Description: "Generate YAML manifests for captain deployments based on the provided configuration.",
		Responses: map[string]*huma.Response{
			"200": {Description: "Captain manifests YAML", Content: map[string]*huma.MediaType{"text/plain": {Schema: &huma.Schema{Type: "string"}}}},
		},
	}, handlers.CreateCaptainManifests)

	// Start HTTP server on 0.0.0.0:8000.
	addr := "0.0.0.0:8000"
	srv := &http.Server{
		Addr:    addr,
		Handler: router,
	}

	// Start server in a goroutine.
	go func() {
		slog.Info("starting server", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server failed", "error", err)
			os.Exit(1)
		}
	}()

	// Graceful shutdown on SIGTERM/SIGINT (risk H4).
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)
	sig := <-quit
	slog.Info("shutting down server", "signal", sig.String())

	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("server forced shutdown", "error", err)
	}
	slog.Info("server stopped")
}

// auditLogMiddleware logs every request with the authenticated user identity
// from oauth2-proxy headers (X-Forwarded-User or X-Forwarded-Email).
func auditLogMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user := r.Header.Get("X-Forwarded-User")
		email := r.Header.Get("X-Forwarded-Email")
		slog.Info("request",
			"method", r.Method,
			"path", r.URL.Path,
			"remote_addr", r.RemoteAddr,
			"user", user,
			"email", email,
		)
		next.ServeHTTP(w, r)
	})
}

func parseLogLevel(s string) slog.Level {
	switch strings.ToUpper(s) {
	case "DEBUG":
		return slog.LevelDebug
	case "WARN", "WARNING":
		return slog.LevelWarn
	case "ERROR":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}

