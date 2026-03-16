package github

import (
	"context"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"regexp"
	"time"
)

const (
	githubAPIVersion = "2026-03-10"
	repo             = "internal-GlueOps/gha-tools-api"
	repoAPIBase      = "https://api.github.com/repos/" + repo
	repoHTMLBase     = "https://github.com/" + repo
	requestTimeout   = 30 * time.Second
	pollInterval     = 2 * time.Second
	pollMaxAttempts  = 6
)

// runURLPattern matches GitHub Actions run URLs. The $ anchor prevents partial matches.
var runURLPattern = regexp.MustCompile(`^https://github\.com/([^/]+/[^/]+)/actions/runs/(\d+)$`)

// RunInfo holds the nullable run ID and run URL from polling.
type RunInfo struct {
	RunID  *int
	RunURL *string
}

// WorkflowRunStatus holds the status details of a workflow run from the GitHub API.
type WorkflowRunStatus struct {
	RunID      int
	Name       *string
	Status     string
	Conclusion *string
	RunURL     string
	CreatedAt  *string
	UpdatedAt  *string
}

// pythonBool returns "True" or "False" to match Python's str(bool) capitalization (risk H3).
func pythonBool(v bool) string {
	if v {
		return "True"
	}
	return "False"
}

// newGitHubRequest creates an HTTP request with GitHub API authentication headers.
// Reads GITHUB_TOKEN lazily per-request (risk C3: fail lazily, not at startup).
func newGitHubRequest(ctx context.Context, method, url string, body io.Reader) (*http.Request, error) {
	token := os.Getenv("GITHUB_TOKEN")
	if token == "" {
		return nil, fmt.Errorf("GITHUB_TOKEN environment variable is not set")
	}

	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("X-GitHub-Api-Version", githubAPIVersion)
	return req, nil
}

// httpClient returns an HTTP client with the standard 30-second timeout.
func httpClient() *http.Client {
	return &http.Client{Timeout: requestTimeout}
}

// CallGitHubWorkflow dispatches a GitHub Actions workflow via the dispatch API.
// Returns the HTTP status code. Payload always includes "ref": "refs/heads/main".
func CallGitHubWorkflow(ctx context.Context, dispatchURL string, inputs map[string]string) (int, error) {
	payload := map[string]interface{}{
		"ref": "refs/heads/main",
	}
	if len(inputs) > 0 {
		payload["inputs"] = inputs
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return 0, fmt.Errorf("failed to marshal dispatch payload: %w", err)
	}

	req, err := newGitHubRequest(ctx, http.MethodPost, dispatchURL, bytes.NewReader(payloadBytes))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient().Do(req)
	if err != nil {
		return 0, fmt.Errorf("GitHub workflow dispatch request failed: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	slog.Info("GitHub workflow dispatch",
		"url", dispatchURL,
		"inputs", inputs,
		"status_code", resp.StatusCode,
	)
	return resp.StatusCode, nil
}

// GetWorkflowRunID polls for the most recent run of a workflow that was just dispatched.
// Python sleeps FIRST then checks (sleep → request → sleep → request, 6 iterations).
// Returns nullable RunID and RunURL; nil pointers when polling times out (risk C2).
// Uses context.Context with select + time.After for cancellation support.
func GetWorkflowRunID(ctx context.Context, workflowFile string) (*RunInfo, error) {
	url := fmt.Sprintf("%s/actions/workflows/%s/runs", repoAPIBase, workflowFile)

	for attempt := 0; attempt < pollMaxAttempts; attempt++ {
		// Sleep first, then check (matching Python behavior).
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(pollInterval):
		}

		req, err := newGitHubRequest(ctx, http.MethodGet, url, nil)
		if err != nil {
			return nil, err
		}
		q := req.URL.Query()
		q.Set("per_page", "1")
		req.URL.RawQuery = q.Encode()

		resp, err := httpClient().Do(req)
		if err != nil {
			slog.Info("polling for workflow run failed",
				"attempt", attempt+1,
				"max_attempts", pollMaxAttempts,
				"workflow_file", workflowFile,
				"error", err,
			)
			continue
		}

		if resp.StatusCode == http.StatusOK {
			var result struct {
				WorkflowRuns []struct {
					ID      int    `json:"id"`
					HTMLURL string `json:"html_url"`
				} `json:"workflow_runs"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
				_ = resp.Body.Close()
				slog.Warn("failed to decode workflow runs response", "error", err)
				continue
			}
			_ = resp.Body.Close()

			if len(result.WorkflowRuns) > 0 {
				run := result.WorkflowRuns[0]
				slog.Info("found workflow run",
					"run_id", run.ID,
					"workflow_file", workflowFile,
				)
				runID := run.ID
				runURL := run.HTMLURL
				return &RunInfo{RunID: &runID, RunURL: &runURL}, nil
			}
		} else {
			_ = resp.Body.Close()
		}

		slog.Info("polling for workflow run",
			"attempt", attempt+1,
			"max_attempts", pollMaxAttempts,
			"workflow_file", workflowFile,
		)
	}

	slog.Warn("could not find workflow run after polling", "workflow_file", workflowFile)
	return &RunInfo{RunID: nil, RunURL: nil}, nil
}

// DispatchAndGetRun dispatches a workflow and polls for the run details.
// On non-2xx dispatch status, returns an error (results in 500, matching Python ValueError behavior).
func DispatchAndGetRun(ctx context.Context, workflowFile string, inputs map[string]string) (statusCode int, allJobsURL string, runInfo *RunInfo, err error) {
	dispatchURL := fmt.Sprintf("%s/actions/workflows/%s/dispatches", repoAPIBase, workflowFile)
	allJobsURL = fmt.Sprintf("%s/actions/workflows/%s", repoHTMLBase, workflowFile)

	statusCode, err = CallGitHubWorkflow(ctx, dispatchURL, inputs)
	if err != nil {
		return 0, "", nil, err
	}
	if statusCode < 200 || statusCode >= 300 {
		return 0, "", nil, fmt.Errorf("GitHub workflow dispatch failed with status %d", statusCode)
	}

	runInfo, err = GetWorkflowRunID(ctx, workflowFile)
	if err != nil {
		return 0, "", nil, err
	}

	return statusCode, allJobsURL, runInfo, nil
}

// GetWorkflowRunStatus parses a GitHub Actions run URL, fetches the run status from the API,
// and returns the status details. Returns specific HTTP errors matching Python behavior (risk H2).
func GetWorkflowRunStatus(ctx context.Context, runURL string) (*WorkflowRunStatus, error) {
	match := runURLPattern.FindStringSubmatch(runURL)
	if match == nil {
		return nil, hError(http.StatusBadRequest, fmt.Sprintf("Invalid GitHub Actions run URL: %s", runURL))
	}

	ownerRepo := match[1]
	runID := match[2]
	apiURL := fmt.Sprintf("https://api.github.com/repos/%s/actions/runs/%s", ownerRepo, runID)

	req, err := newGitHubRequest(ctx, http.MethodGet, apiURL, nil)
	if err != nil {
		return nil, err
	}

	resp, err := httpClient().Do(req)
	if err != nil {
		return nil, fmt.Errorf("GitHub API request failed: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return nil, hError(http.StatusBadGateway, fmt.Sprintf("GitHub API returned %d for run %s", resp.StatusCode, runID))
	}

	var data struct {
		ID         int     `json:"id"`
		Name       *string `json:"name"`
		Status     string  `json:"status"`
		Conclusion *string `json:"conclusion"`
		HTMLURL    string  `json:"html_url"`
		CreatedAt  *string `json:"created_at"`
		UpdatedAt  *string `json:"updated_at"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, fmt.Errorf("failed to decode workflow run status: %w", err)
	}

	return &WorkflowRunStatus{
		RunID:      data.ID,
		Name:       data.Name,
		Status:     data.Status,
		Conclusion: data.Conclusion,
		RunURL:     data.HTMLURL,
		CreatedAt:  data.CreatedAt,
		UpdatedAt:  data.UpdatedAt,
	}, nil
}

// NukeAwsAccountWorkflow dispatches the aws-nuke-account workflow.
func NukeAwsAccountWorkflow(ctx context.Context, awsSubAccountName string) (int, string, *RunInfo, error) {
	return DispatchAndGetRun(ctx, "aws-nuke-account.yml", map[string]string{
		"AWS_ACCOUNT_NAME_TO_NUKE": awsSubAccountName,
	})
}

// NukeCaptainDomainDataAndBackups dispatches the nuke-captain-domain-data-and-backups workflow.
func NukeCaptainDomainDataAndBackups(ctx context.Context, captainDomain string) (int, string, *RunInfo, error) {
	return DispatchAndGetRun(ctx, "nuke-captain-domain-data-and-backups.yml", map[string]string{
		"CAPTAIN_DOMAIN_TO_NUKE": captainDomain,
	})
}

// ResetTenantGitHubOrganization dispatches the reset-tenant-github-organization workflow.
// Boolean values use Python-compatible "True"/"False" capitalization (risk H3).
func ResetTenantGitHubOrganization(ctx context.Context, captainDomain string, deleteAllRepos bool, customDomain string, enableCustomDomain bool) (int, string, *RunInfo, error) {
	return DispatchAndGetRun(ctx, "reset-tenant-github-organization.yml", map[string]string{
		"CAPTAIN_DOMAIN":             captainDomain,
		"DELETE_ALL_EXISTING_REPOS":  pythonBool(deleteAllRepos),
		"CUSTOM_DOMAIN":              customDomain,
		"ENABLE_CUSTOM_DOMAIN":       pythonBool(enableCustomDomain),
	})
}

// httpError implements error with an HTTP status code for Huma error handling (risk H2).
type httpError struct {
	status int
	detail string
}

func (e *httpError) Error() string  { return e.detail }
func (e *httpError) GetStatus() int { return e.status }

func hError(status int, detail string) error {
	return &httpError{status: status, detail: detail}
}
