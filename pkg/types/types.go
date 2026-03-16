package types

// ---- Response Types ----

// HealthResponse represents the health check response.
type HealthResponse struct {
	Body struct {
		Status string `json:"status" example:"healthy" doc:"Health status"`
	}
}

// VersionResponse represents the version information returned by GET /version.
type VersionResponse struct {
	Body struct {
		Version        string `json:"version" example:"v1.0.0" doc:"Application version"`
		CommitSHA      string `json:"commit_sha" example:"abc1234567890def1234567890abcdef12345678" doc:"Full commit SHA"`
		ShortSHA       string `json:"short_sha" example:"abc1234" doc:"Short commit SHA"`
		BuildTimestamp string `json:"build_timestamp" example:"2026-01-01T00:00:00Z" doc:"Build timestamp"`
		GitRef         string `json:"git_ref" example:"main" doc:"Git ref used for the build"`
	}
}

// MessageResponse represents a simple message response.
type MessageResponse struct {
	Body struct {
		Message string `json:"message" example:"Success" doc:"Response message"`
	}
}

// WorkflowDispatchResponse represents the response from GitHub workflow dispatch endpoints.
type WorkflowDispatchResponse struct {
	Body struct {
		StatusCode int     `json:"status_code" example:"200" doc:"HTTP status code from GitHub API"`
		RunID      *int    `json:"run_id" doc:"Workflow run ID, null if polling timed out"`
		RunURL     *string `json:"run_url" doc:"URL to the workflow run, null if polling timed out"`
		AllJobsURL string  `json:"all_jobs_url" example:"https://github.com/org/repo/actions/runs/12345678/jobs" doc:"URL to view all jobs for the workflow run"`
	}
}

// WorkflowRunStatusResponse represents the response from the workflow run status endpoint.
type WorkflowRunStatusResponse struct {
	Body struct {
		RunID      int     `json:"run_id" example:"12345678" doc:"Workflow run ID"`
		Name       *string `json:"name" doc:"Workflow run name"`
		Status     string  `json:"status" example:"completed" doc:"Current status of the workflow run"`
		Conclusion *string `json:"conclusion" doc:"Conclusion of the workflow run, null if still in progress"`
		RunURL     string  `json:"run_url" example:"https://github.com/org/repo/actions/runs/12345678" doc:"URL to the workflow run"`
		CreatedAt  *string `json:"created_at" doc:"Timestamp when the workflow run was created"`
		UpdatedAt  *string `json:"updated_at" doc:"Timestamp when the workflow run was last updated"`
	}
}

// ErrorResponse is the standard error format for the API.
// It implements error and huma.StatusError so Huma serializes it directly.
type ErrorResponse struct {
	Status int    `json:"status" example:"500" doc:"HTTP status code"`
	Detail string `json:"detail" example:"An internal server error occurred." doc:"Error detail message"`
}

// Error implements the error interface.
func (e *ErrorResponse) Error() string {
	return e.Detail
}

// GetStatus implements huma.StatusError so Huma uses this status code.
func (e *ErrorResponse) GetStatus() int {
	return e.Status
}

// ---- Request Types ----

// ChiselNodesRequest is the request body for creating Chisel exit nodes.
type ChiselNodesRequest struct {
	Body struct {
		CaptainDomain string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
		NodeCount     int    `json:"node_count" minimum:"1" maximum:"6" default:"3" example:"3" doc:"Number of exit nodes to create (1-6, default: 3)"`
	}
}

// ChiselNodesDeleteRequest is the request body for deleting Chisel exit nodes.
type ChiselNodesDeleteRequest struct {
	Body struct {
		CaptainDomain string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
	}
}

// StorageBucketsRequest is the request body for creating storage buckets.
type StorageBucketsRequest struct {
	Body struct {
		CaptainDomain string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
	}
}

// AwsCredentialsRequest is the request body for retrieving AWS credentials.
type AwsCredentialsRequest struct {
	Body struct {
		AwsSubAccountName string `json:"aws_sub_account_name" minLength:"1" example:"glueops-captain-foobar" doc:"AWS sub-account name"`
	}
}

// AwsNukeAccountRequest is the request body for nuking an AWS account.
type AwsNukeAccountRequest struct {
	Body struct {
		AwsSubAccountName string `json:"aws_sub_account_name" minLength:"1" example:"glueops-captain-foobar" doc:"AWS sub-account name"`
	}
}

// CaptainDomainNukeDataAndBackupsRequest is the request body for nuking captain domain data and backups.
type CaptainDomainNukeDataAndBackupsRequest struct {
	Body struct {
		CaptainDomain string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
	}
}

// ResetGitHubOrganizationRequest is the request body for resetting a GitHub organization.
type ResetGitHubOrganizationRequest struct {
	Body struct {
		CaptainDomain         string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
		DeleteAllExistingRepos bool   `json:"delete_all_existing_repos" example:"true" doc:"Whether to delete all existing repos in the organization"`
		CustomDomain          string `json:"custom_domain" minLength:"1" example:"example.com" doc:"Custom domain for the organization"`
		EnableCustomDomain    bool   `json:"enable_custom_domain" example:"false" doc:"Whether to enable the custom domain"`
	}
}

// OpsgenieAlertsManifestRequest is the request body for generating Opsgenie alerts manifest.
type OpsgenieAlertsManifestRequest struct {
	Body struct {
		CaptainDomain  string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
		OpsgenieAPIKey string `json:"opsgenie_api_key" minLength:"1" example:"6825b4ef-4e84-44a1-8450-b46b02852add" doc:"Opsgenie API key"`
	}
}

// CaptainManifestsRequest is the request body for generating captain manifests.
type CaptainManifestsRequest struct {
	Body struct {
		CaptainDomain                              string `json:"captain_domain" minLength:"1" example:"nonprod.foobar.onglueops.rocks" doc:"Captain domain for the cluster"`
		TenantGitHubOrganizationName               string `json:"tenant_github_organization_name" minLength:"1" example:"development-tenant-foobar" doc:"Tenant GitHub organization name"`
		TenantDeploymentConfigurationsRepoName string `json:"tenant_deployment_configurations_repository_name" minLength:"1" example:"deployment-configurations" doc:"Tenant deployment configurations repository name"`
	}
}

// GitHubWorkflowRunStatusRequest is the request input for checking workflow run status.
type GitHubWorkflowRunStatusRequest struct {
	RunURL string `query:"run_url" required:"true" minLength:"1" example:"https://github.com/internal-GlueOps/gha-tools-api/actions/runs/12345678" doc:"GitHub Actions run URL"`
}
