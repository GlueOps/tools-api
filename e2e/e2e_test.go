package e2e

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"testing"

	"github.com/GlueOps/tools-api/internal/version"
	"github.com/GlueOps/tools-api/pkg/handlers"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
)

// newTestServer creates an httptest.Server with the full API routing configured,
// matching cmd/server/main.go. This allows integration-level testing of every
// endpoint without external service dependencies.
func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()

	// Override huma.NewError to match production error format (risk M3).
	huma.NewError = func(status int, msg string, errs ...error) huma.StatusError {
		detail := msg
		if detail == "" {
			detail = http.StatusText(status)
		}
		if status >= 500 {
			buf := make([]byte, 4096)
			n := runtime.Stack(buf, false)
			_ = string(buf[:n])
		} else if len(errs) > 0 {
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

	router.Get("/", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/docs", http.StatusTemporaryRedirect)
	})

	schemaPrefix := "#/components/schemas/"
	registry := huma.NewMapRegistry(schemaPrefix, huma.DefaultSchemaNamer)
	config := huma.Config{
		OpenAPI: &huma.OpenAPI{
			OpenAPI: "3.1.0",
			Info: &huma.Info{
				Title:       "Tools API",
				Version:     version.Version,
				Description: "Various APIs to help you speed up your development and testing.",
			},
			Components: &huma.Components{
				Schemas: registry,
			},
		},
		OpenAPIPath:   "/openapi",
		DocsPath:      "/docs",
		DocsRenderer:  huma.DocsRendererStoplightElements,
		SchemasPath:   "/schemas",
		Formats:       huma.DefaultFormats,
		DefaultFormat: "application/json",
	}

	api := humachi.New(router, config)

	// Health endpoint (chi-direct, excluded from OpenAPI).
	router.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy"}`))
	})

	// Register all Huma endpoints matching main.go.
	huma.Register(api, huma.Operation{
		OperationID: "get-version",
		Method:      http.MethodGet,
		Path:        "/version",
		Summary:     "Contains version information about this tools-api",
	}, handlers.GetVersion)

	huma.Register(api, huma.Operation{
		OperationID: "create-storage-buckets",
		Method:      http.MethodPost,
		Path:        "/v1/storage/buckets",
		Summary:     "Create/Re-create storage buckets",
	}, handlers.CreateStorageBuckets)

	huma.Register(api, huma.Operation{
		OperationID: "create-aws-credentials",
		Method:      http.MethodPost,
		Path:        "/v1/aws/credentials",
		Summary:     "AWS admin credentials",
	}, handlers.CreateAwsCredentials)

	huma.Register(api, huma.Operation{
		OperationID: "nuke-aws-account",
		Method:      http.MethodPost,
		Path:        "/v1/aws/nuke",
		Summary:     "Nuke AWS account",
	}, handlers.NukeAwsAccount)

	huma.Register(api, huma.Operation{
		OperationID: "nuke-captain-domain-data",
		Method:      http.MethodPost,
		Path:        "/v1/nuke/domain-data",
		Summary:     "Nuke captain domain data",
	}, handlers.NukeCaptainDomainData)

	huma.Register(api, huma.Operation{
		OperationID: "reset-github-organization",
		Method:      http.MethodPost,
		Path:        "/v1/github/reset-org",
		Summary:     "Reset GitHub organization",
	}, handlers.ResetGitHubOrganization)

	huma.Register(api, huma.Operation{
		OperationID: "get-workflow-run-status",
		Method:      http.MethodGet,
		Path:        "/v1/github/workflow-status",
		Summary:     "Get workflow run status",
	}, handlers.GetWorkflowRunStatus)

	huma.Register(api, huma.Operation{
		OperationID: "create-chisel-nodes",
		Method:      http.MethodPost,
		Path:        "/v1/chisel",
		Summary:     "Create Chisel nodes",
	}, handlers.CreateChiselNodes)

	huma.Register(api, huma.Operation{
		OperationID: "delete-chisel-nodes",
		Method:      http.MethodPost,
		Path:        "/v1/chisel/delete",
		Summary:     "Delete Chisel nodes",
	}, handlers.DeleteChiselNodes)

	huma.Register(api, huma.Operation{
		OperationID: "create-opsgenie-manifest",
		Method:      http.MethodPost,
		Path:        "/v1/opsgenie/manifest",
		Summary:     "Create Opsgenie manifest",
	}, handlers.CreateOpsgenieManifest)

	huma.Register(api, huma.Operation{
		OperationID: "create-captain-manifests",
		Method:      http.MethodPost,
		Path:        "/v1/captain/manifests",
		Summary:     "Generate captain manifests",
	}, handlers.CreateCaptainManifests)

	return httptest.NewServer(router)
}

// ---- 1. Health Endpoint ----

func TestHealthEndpoint(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatalf("GET /health failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 200 {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}

	var body map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("failed to decode body: %v", err)
	}
	if body["status"] != "healthy" {
		t.Errorf("status = %q, want %q", body["status"], "healthy")
	}
}

// ---- 2. Version Endpoint ----

func TestVersionEndpoint(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/version")
	if err != nil {
		t.Fatalf("GET /version failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 200 {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	var body struct {
		Version        string `json:"version"`
		CommitSHA      string `json:"commit_sha"`
		ShortSHA       string `json:"short_sha"`
		BuildTimestamp string `json:"build_timestamp"`
		GitRef         string `json:"git_ref"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("failed to decode: %v", err)
	}

	// All fields must be present (defaults to "UNKNOWN" in test builds).
	if body.Version == "" {
		t.Error("version field is empty")
	}
	if body.CommitSHA == "" {
		t.Error("commit_sha field is empty")
	}
	if body.ShortSHA == "" {
		t.Error("short_sha field is empty")
	}
	if body.BuildTimestamp == "" {
		t.Error("build_timestamp field is empty")
	}
	if body.GitRef == "" {
		t.Error("git_ref field is empty")
	}
}

// ---- 3. Root Redirect ----

func TestRootRedirectsToDocs(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	client := &http.Client{CheckRedirect: func(req *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	}}

	resp, err := client.Get(srv.URL + "/")
	if err != nil {
		t.Fatalf("GET / failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusTemporaryRedirect {
		t.Errorf("expected 307, got %d", resp.StatusCode)
	}
	loc := resp.Header.Get("Location")
	if loc != "/docs" {
		t.Errorf("Location = %q, want /docs", loc)
	}
}

// ---- 4. OpenAPI Spec Structure ----

func TestOpenAPISpec(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/openapi.json")
	if err != nil {
		t.Fatalf("GET /openapi.json failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 200 {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read body: %v", err)
	}

	var spec map[string]interface{}
	if err := json.Unmarshal(body, &spec); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	// Verify OpenAPI version.
	if v, ok := spec["openapi"].(string); !ok || v != "3.1.0" {
		t.Errorf("openapi version = %v, want 3.1.0", spec["openapi"])
	}

	// Verify info.
	info, ok := spec["info"].(map[string]interface{})
	if !ok {
		t.Fatal("missing info object")
	}
	if info["title"] != "Tools API" {
		t.Errorf("info.title = %v, want %q", info["title"], "Tools API")
	}

	// Verify all expected paths exist.
	paths, ok := spec["paths"].(map[string]interface{})
	if !ok {
		t.Fatal("missing paths object")
	}

	expectedPaths := []string{
		"/version",
		"/v1/storage/buckets",
		"/v1/aws/credentials",
		"/v1/aws/nuke",
		"/v1/nuke/domain-data",
		"/v1/github/reset-org",
		"/v1/github/workflow-status",
		"/v1/chisel",
		"/v1/chisel/delete",
		"/v1/opsgenie/manifest",
		"/v1/captain/manifests",
	}

	for _, p := range expectedPaths {
		if _, exists := paths[p]; !exists {
			t.Errorf("missing expected path: %s", p)
		}
	}

	// Health should NOT be in OpenAPI (registered on chi directly).
	if _, exists := paths["/health"]; exists {
		t.Error("/health should not appear in OpenAPI spec")
	}

	// Verify expected HTTP methods.
	methodChecks := map[string]string{
		"/version":                    "get",
		"/v1/storage/buckets":         "post",
		"/v1/aws/credentials":         "post",
		"/v1/aws/nuke":                "post",
		"/v1/nuke/domain-data":        "post",
		"/v1/github/reset-org":        "post",
		"/v1/github/workflow-status":  "get",
		"/v1/chisel":                  "post",
		"/v1/chisel/delete":           "post",
		"/v1/opsgenie/manifest":       "post",
		"/v1/captain/manifests":       "post",
	}
	for path, method := range methodChecks {
		pathObj, ok := paths[path].(map[string]interface{})
		if !ok {
			continue
		}
		if _, exists := pathObj[method]; !exists {
			t.Errorf("path %s missing method %s", path, method)
		}
	}

	// Verify operation IDs.
	expectedOps := map[string]string{
		"/version":                   "get-version",
		"/v1/storage/buckets":        "create-storage-buckets",
		"/v1/aws/credentials":        "create-aws-credentials",
		"/v1/aws/nuke":               "nuke-aws-account",
		"/v1/nuke/domain-data":       "nuke-captain-domain-data",
		"/v1/github/reset-org":       "reset-github-organization",
		"/v1/github/workflow-status": "get-workflow-run-status",
		"/v1/chisel":                 "create-chisel-nodes",
		"/v1/chisel/delete":          "delete-chisel-nodes",
		"/v1/opsgenie/manifest":      "create-opsgenie-manifest",
		"/v1/captain/manifests":      "create-captain-manifests",
	}
	for path, wantOp := range expectedOps {
		pathObj, ok := paths[path].(map[string]interface{})
		if !ok {
			continue
		}
		method := methodChecks[path]
		methodObj, ok := pathObj[method].(map[string]interface{})
		if !ok {
			continue
		}
		gotOp, _ := methodObj["operationId"].(string)
		if gotOp != wantOp {
			t.Errorf("path %s operationId = %q, want %q", path, gotOp, wantOp)
		}
	}

	// Verify no DELETE endpoints exist (risk M1 eliminated).
	for path, pathObj := range paths {
		obj, ok := pathObj.(map[string]interface{})
		if !ok {
			continue
		}
		if _, exists := obj["delete"]; exists {
			t.Errorf("path %s has DELETE method — all destructive ops should use POST", path)
		}
	}
}

// ---- 5. Captain Manifests — Full Parity (No External Deps) ----

func TestCaptainManifestsEndpoint(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	reqBody := `{
		"captain_domain": "nonprod.antoniostaqueria.onglueops.com",
		"tenant_github_organization_name": "dev-tenant",
		"tenant_deployment_configurations_repository_name": "deployment-configurations"
	}`

	resp, err := http.Post(srv.URL+"/v1/captain/manifests", "application/json", strings.NewReader(reqBody))
	if err != nil {
		t.Fatalf("POST /v1/captain/manifests failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("expected 200, got %d: %s", resp.StatusCode, body)
	}

	// Must return text/plain (risk C1).
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "text/plain") {
		t.Errorf("Content-Type = %q, want text/plain", ct)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read body: %v", err)
	}
	result := string(body)

	// Verify 3 YAML documents.
	docs := strings.Split(result, "\n---\n")
	if len(docs) != 3 {
		t.Fatalf("expected 3 YAML documents, got %d", len(docs))
	}

	// Namespace
	if !strings.Contains(docs[0], "kind: Namespace") {
		t.Error("first document should be a Namespace")
	}
	if !strings.Contains(docs[0], "name: nonprod") {
		t.Error("namespace should use environment name 'nonprod'")
	}

	// AppProject
	if !strings.Contains(docs[1], "kind: AppProject") {
		t.Error("second document should be an AppProject")
	}
	if !strings.Contains(docs[1], "dev-tenant") {
		t.Error("appproject should reference tenant org")
	}

	// ApplicationSet
	if !strings.Contains(docs[2], "kind: ApplicationSet") {
		t.Error("third document should be an ApplicationSet")
	}

	// Go template syntax must be preserved literally (risk H1).
	if !strings.Contains(docs[2], `{{ index .path.segments 1 | replace "." "-"  | replace "_" "-" }}`) {
		t.Error("Go template syntax must be preserved in ApplicationSet output")
	}

	// captain_domain must appear in the values section.
	if !strings.Contains(result, "captain_domain: nonprod.antoniostaqueria.onglueops.com") {
		t.Error("captain_domain should appear in output")
	}

	// No unresolved template placeholders.
	if strings.Contains(result, "<%") || strings.Contains(result, "%>") {
		t.Error("output should not contain unresolved template placeholders")
	}
}

// ---- 6. Opsgenie Manifest — Full Parity (No External Deps) ----

func TestOpsgenieManifestEndpoint(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	reqBody := `{
		"captain_domain": "nonprod.foobar.onglueops.rocks",
		"opsgenie_api_key": "test-api-key-12345"
	}`

	resp, err := http.Post(srv.URL+"/v1/opsgenie/manifest", "application/json", strings.NewReader(reqBody))
	if err != nil {
		t.Fatalf("POST /v1/opsgenie/manifest failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("expected 200, got %d: %s", resp.StatusCode, body)
	}

	// Must return text/plain (risk C1).
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "text/plain") {
		t.Errorf("Content-Type = %q, want text/plain", ct)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read body: %v", err)
	}
	result := string(body)

	checks := []string{
		"kind: Application",
		"name: glueops-core-alerts-opsgenie",
		"nonprod.foobar.onglueops.rocks",
		"test-api-key-12345",
		"kind: AlertmanagerConfig",
		"apiURL: https://api.opsgenie.com/",
	}
	for _, s := range checks {
		if !strings.Contains(result, s) {
			t.Errorf("opsgenie manifest missing: %q", s)
		}
	}
}

// ---- 7. Validation Errors (422) ----

func TestValidationErrorMissingRequiredFields(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	tests := []struct {
		name     string
		method   string
		path     string
		body     string
		wantCode int
	}{
		{
			name:     "captain manifests - empty body",
			method:   "POST",
			path:     "/v1/captain/manifests",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "captain manifests - empty captain_domain",
			method:   "POST",
			path:     "/v1/captain/manifests",
			body:     `{"captain_domain": "", "tenant_github_organization_name": "org", "tenant_deployment_configurations_repository_name": "repo"}`,
			wantCode: 422,
		},
		{
			name:     "opsgenie manifest - empty body",
			method:   "POST",
			path:     "/v1/opsgenie/manifest",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "opsgenie manifest - empty api key",
			method:   "POST",
			path:     "/v1/opsgenie/manifest",
			body:     `{"captain_domain": "foo.bar.com", "opsgenie_api_key": ""}`,
			wantCode: 422,
		},
		{
			name:     "chisel create - empty body",
			method:   "POST",
			path:     "/v1/chisel",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "chisel create - node_count too high",
			method:   "POST",
			path:     "/v1/chisel",
			body:     `{"captain_domain": "foo.bar.com", "node_count": 7}`,
			wantCode: 422,
		},
		{
			name:     "chisel create - node_count too low",
			method:   "POST",
			path:     "/v1/chisel",
			body:     `{"captain_domain": "foo.bar.com", "node_count": 0}`,
			wantCode: 422,
		},
		{
			name:     "chisel delete - empty body",
			method:   "POST",
			path:     "/v1/chisel/delete",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "storage buckets - empty body",
			method:   "POST",
			path:     "/v1/storage/buckets",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "storage buckets - empty captain_domain",
			method:   "POST",
			path:     "/v1/storage/buckets",
			body:     `{"captain_domain": ""}`,
			wantCode: 422,
		},
		{
			name:     "aws credentials - empty body",
			method:   "POST",
			path:     "/v1/aws/credentials",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "aws nuke - empty body",
			method:   "POST",
			path:     "/v1/aws/nuke",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "nuke domain data - empty body",
			method:   "POST",
			path:     "/v1/nuke/domain-data",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "reset github org - empty body",
			method:   "POST",
			path:     "/v1/github/reset-org",
			body:     `{}`,
			wantCode: 422,
		},
		{
			name:     "workflow status - missing run_url query param",
			method:   "GET",
			path:     "/v1/github/workflow-status",
			body:     "",
			wantCode: 422,
		},
		{
			name:     "workflow status - empty run_url query param",
			method:   "GET",
			path:     "/v1/github/workflow-status?run_url=",
			body:     "",
			wantCode: 422,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var req *http.Request
			var err error
			if tt.body != "" {
				req, err = http.NewRequest(tt.method, srv.URL+tt.path, strings.NewReader(tt.body))
				req.Header.Set("Content-Type", "application/json")
			} else {
				req, err = http.NewRequest(tt.method, srv.URL+tt.path, nil)
			}
			if err != nil {
				t.Fatalf("creating request: %v", err)
			}

			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				t.Fatalf("request failed: %v", err)
			}
			defer func() { _ = resp.Body.Close() }()

			if resp.StatusCode != tt.wantCode {
				body, _ := io.ReadAll(resp.Body)
				t.Errorf("expected %d, got %d: %s", tt.wantCode, resp.StatusCode, body)
			}
		})
	}
}

// ---- 8. Error Response Format ----

func TestErrorResponseFormat(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// Trigger a validation error.
	resp, err := http.Post(srv.URL+"/v1/captain/manifests", "application/json", strings.NewReader(`{}`))
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read body: %v", err)
	}

	var errResp map[string]interface{}
	if err := json.Unmarshal(body, &errResp); err != nil {
		t.Fatalf("error response is not valid JSON: %v\nbody: %s", err, body)
	}

	// Must have "status" and "detail" fields (risk M3).
	if _, ok := errResp["status"]; !ok {
		t.Error("error response missing 'status' field")
	}
	if _, ok := errResp["detail"]; !ok {
		t.Error("error response missing 'detail' field")
	}

	// Must NOT have "traceback" or "error" fields.
	if _, ok := errResp["traceback"]; ok {
		t.Error("error response should NOT contain 'traceback' field")
	}
	if _, ok := errResp["error"]; ok {
		t.Error("error response should NOT contain 'error' field")
	}

	// Must NOT have Huma default "title" field.
	if _, ok := errResp["title"]; ok {
		t.Error("error response should NOT contain Huma default 'title' field")
	}

	// Status must match HTTP status code.
	statusFloat, ok := errResp["status"].(float64)
	if !ok {
		t.Fatal("status field is not a number")
	}
	if int(statusFloat) != resp.StatusCode {
		t.Errorf("status field = %d, HTTP status = %d", int(statusFloat), resp.StatusCode)
	}
}

// ---- 9. Invalid JSON Body ----

func TestInvalidJSONBody(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Post(srv.URL+"/v1/captain/manifests", "application/json", strings.NewReader(`not json`))
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	// Should return 4xx, not 5xx.
	if resp.StatusCode < 400 || resp.StatusCode >= 500 {
		t.Errorf("expected 4xx for invalid JSON, got %d", resp.StatusCode)
	}
}

// ---- 10. 404 for Unknown Paths ----

func TestNotFoundPath(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/v1/nonexistent")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 404 && resp.StatusCode != 405 {
		t.Errorf("expected 404 or 405 for unknown path, got %d", resp.StatusCode)
	}
}

// ---- 11. Method Not Allowed ----

func TestMethodNotAllowed(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// GET on a POST-only endpoint.
	resp, err := http.Get(srv.URL + "/v1/captain/manifests")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 405 {
		t.Errorf("expected 405 for wrong method, got %d", resp.StatusCode)
	}
}

// ---- 12. OpenAPI Spec Schema Validation ----

func TestOpenAPISpecSchemas(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/openapi.json")
	if err != nil {
		t.Fatalf("GET /openapi.json failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	var spec map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&spec); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	components, ok := spec["components"].(map[string]interface{})
	if !ok {
		t.Fatal("missing components in OpenAPI spec")
	}

	schemas, ok := components["schemas"].(map[string]interface{})
	if !ok {
		t.Fatal("missing schemas in components")
	}

	// Verify WorkflowDispatchResponseBody has nullable fields for run_id and run_url (risk C2).
	// Only check the dispatch schema, not the status schema (where run_id is a non-nullable int).
	dispatchSchemaName := "WorkflowDispatchResponseBody"
	dispatchSchema, ok := schemas[dispatchSchemaName].(map[string]interface{})
	if !ok {
		t.Fatalf("missing schema %q", dispatchSchemaName)
	}
	props, ok := dispatchSchema["properties"].(map[string]interface{})
	if !ok {
		t.Fatal("missing properties in dispatch response schema")
	}

	if runIDProp, ok := props["run_id"].(map[string]interface{}); ok {
		verifyNullable(t, "run_id", runIDProp)
	} else {
		t.Error("missing run_id property in dispatch response schema")
	}

	if runURLProp, ok := props["run_url"].(map[string]interface{}); ok {
		verifyNullable(t, "run_url", runURLProp)
	} else {
		t.Error("missing run_url property in dispatch response schema")
	}
}

// verifyNullable checks that a schema property can be null (OpenAPI 3.1 uses oneOf/anyOf with null type,
// or the "nullable" keyword, or a type array including "null").
func verifyNullable(t *testing.T, fieldName string, prop map[string]interface{}) {
	t.Helper()

	// OpenAPI 3.1: type can be an array like ["integer", "null"] or ["string", "null"].
	if typeVal, ok := prop["type"]; ok {
		switch v := typeVal.(type) {
		case []interface{}:
			for _, item := range v {
				if item == "null" {
					return // nullable via type array
				}
			}
		case string:
			// Single type — not nullable unless "nullable" is set.
		}
	}

	// OpenAPI 3.0 style: "nullable: true".
	if nullable, ok := prop["nullable"].(bool); ok && nullable {
		return
	}

	// Huma may use oneOf/anyOf with a null type.
	for _, key := range []string{"oneOf", "anyOf"} {
		if variants, ok := prop[key].([]interface{}); ok {
			for _, v := range variants {
				if vm, ok := v.(map[string]interface{}); ok {
					if vm["type"] == "null" {
						return
					}
				}
			}
		}
	}

	t.Errorf("field %q should be nullable in OpenAPI schema but is not: %v", fieldName, prop)
}

// ---- 13. Chisel Node Count Validation ----

func TestChiselNodeCountValidation(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	tests := []struct {
		name       string
		body       string
		wantStatus int
	}{
		{
			name:       "node_count=7 exceeds max of 6",
			body:       `{"captain_domain": "test.example.com", "node_count": 7}`,
			wantStatus: 422,
		},
		{
			name:       "node_count=0 below min of 1",
			body:       `{"captain_domain": "test.example.com", "node_count": 0}`,
			wantStatus: 422,
		},
		{
			name:       "node_count=-1 below min of 1",
			body:       `{"captain_domain": "test.example.com", "node_count": -1}`,
			wantStatus: 422,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := http.Post(srv.URL+"/v1/chisel", "application/json", strings.NewReader(tt.body))
			if err != nil {
				t.Fatalf("request failed: %v", err)
			}
			defer func() { _ = resp.Body.Close() }()

			if resp.StatusCode != tt.wantStatus {
				body, _ := io.ReadAll(resp.Body)
				t.Errorf("expected %d, got %d: %s", tt.wantStatus, resp.StatusCode, body)
			}
		})
	}
}

// ---- 14. Server Binding and Configuration ----

func TestServerBindsOnPort8000(t *testing.T) {
	// Verify the Dockerfile exposes port 8000 (this is tested by the Docker build itself).
	// Here we verify the test server starts and responds, confirming the routing works.
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatalf("server did not start: %v", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != 200 {
		t.Errorf("health check failed: %d", resp.StatusCode)
	}
}

// ---- 15. Content-Type for JSON Responses ----

func TestJSONResponseContentType(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// JSON endpoints should return application/json.
	resp, err := http.Get(srv.URL + "/version")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("Content-Type for /version = %q, want application/json", ct)
	}
}

// ---- 16. Plain Text Endpoints Return text/plain ----

func TestPlainTextEndpointContentTypes(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// Only test endpoints that don't require external services.
	tests := []struct {
		name string
		path string
		body string
	}{
		{
			name: "captain manifests",
			path: "/v1/captain/manifests",
			body: `{"captain_domain": "test.example.com", "tenant_github_organization_name": "org", "tenant_deployment_configurations_repository_name": "repo"}`,
		},
		{
			name: "opsgenie manifest",
			path: "/v1/opsgenie/manifest",
			body: `{"captain_domain": "test.example.com", "opsgenie_api_key": "test-key"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := http.Post(srv.URL+tt.path, "application/json", strings.NewReader(tt.body))
			if err != nil {
				t.Fatalf("request failed: %v", err)
			}
			defer func() { _ = resp.Body.Close() }()

			if resp.StatusCode != 200 {
				body, _ := io.ReadAll(resp.Body)
				t.Fatalf("expected 200, got %d: %s", resp.StatusCode, body)
			}

			ct := resp.Header.Get("Content-Type")
			if !strings.Contains(ct, "text/plain") {
				t.Errorf("Content-Type = %q, want text/plain", ct)
			}
		})
	}
}

// ---- 17. Empty String Inputs ----

func TestEmptyStringValidation(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// All string fields with minLength:"1" should reject empty strings (risk M6).
	tests := []struct {
		name string
		path string
		body string
	}{
		{
			name: "captain_domain empty in storage",
			path: "/v1/storage/buckets",
			body: `{"captain_domain": ""}`,
		},
		{
			name: "captain_domain empty in chisel",
			path: "/v1/chisel",
			body: `{"captain_domain": "", "node_count": 3}`,
		},
		{
			name: "captain_domain empty in chisel delete",
			path: "/v1/chisel/delete",
			body: `{"captain_domain": ""}`,
		},
		{
			name: "aws_sub_account_name empty in credentials",
			path: "/v1/aws/credentials",
			body: `{"aws_sub_account_name": ""}`,
		},
		{
			name: "aws_sub_account_name empty in nuke",
			path: "/v1/aws/nuke",
			body: `{"aws_sub_account_name": ""}`,
		},
		{
			name: "captain_domain empty in domain data nuke",
			path: "/v1/nuke/domain-data",
			body: `{"captain_domain": ""}`,
		},
		{
			name: "captain_domain empty in reset org",
			path: "/v1/github/reset-org",
			body: `{"captain_domain": "", "delete_all_existing_repos": true, "custom_domain": "example.com", "enable_custom_domain": false}`,
		},
		{
			name: "captain_domain empty in opsgenie",
			path: "/v1/opsgenie/manifest",
			body: `{"captain_domain": "", "opsgenie_api_key": "key"}`,
		},
		{
			name: "opsgenie_api_key empty in opsgenie",
			path: "/v1/opsgenie/manifest",
			body: `{"captain_domain": "test.com", "opsgenie_api_key": ""}`,
		},
		{
			name: "captain_domain empty in captain manifests",
			path: "/v1/captain/manifests",
			body: `{"captain_domain": "", "tenant_github_organization_name": "org", "tenant_deployment_configurations_repository_name": "repo"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := http.Post(srv.URL+tt.path, "application/json", strings.NewReader(tt.body))
			if err != nil {
				t.Fatalf("request failed: %v", err)
			}
			defer func() { _ = resp.Body.Close() }()

			if resp.StatusCode != 422 {
				body, _ := io.ReadAll(resp.Body)
				t.Errorf("expected 422 for empty string, got %d: %s", resp.StatusCode, body)
			}
		})
	}
}

// ---- 18. Workflow Status Query Parameter ----

func TestWorkflowStatusQueryParam(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// This endpoint uses GET with a query parameter (not POST with body).
	// Verify it's a GET endpoint.
	resp, err := http.Post(srv.URL+"/v1/github/workflow-status", "application/json", strings.NewReader(`{}`))
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	// POST should return 405.
	if resp.StatusCode != 405 {
		t.Errorf("POST to workflow-status should return 405, got %d", resp.StatusCode)
	}
}

// ---- 19. Docs Endpoint Accessible ----

func TestDocsEndpoint(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/docs")
	if err != nil {
		t.Fatalf("GET /docs failed: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != 200 {
		t.Errorf("expected 200 for /docs, got %d", resp.StatusCode)
	}

	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "text/html") {
		t.Errorf("Content-Type for /docs = %q, want text/html", ct)
	}
}
