package handlers

import (
	"context"

	"github.com/GlueOps/tools-api/pkg/github"
	"github.com/GlueOps/tools-api/pkg/types"
)

// NukeAwsAccount handles POST /v1/aws/nuke.
func NukeAwsAccount(ctx context.Context, input *types.AwsNukeAccountRequest) (*types.WorkflowDispatchResponse, error) {
	statusCode, allJobsURL, runInfo, err := github.NukeAwsAccountWorkflow(ctx, input.Body.AwsSubAccountName)
	if err != nil {
		return nil, err
	}
	return buildDispatchResponse(statusCode, allJobsURL, runInfo), nil
}

// NukeCaptainDomainData handles POST /v1/nuke/domain-data.
func NukeCaptainDomainData(ctx context.Context, input *types.CaptainDomainNukeDataAndBackupsRequest) (*types.WorkflowDispatchResponse, error) {
	statusCode, allJobsURL, runInfo, err := github.NukeCaptainDomainDataAndBackups(ctx, input.Body.CaptainDomain)
	if err != nil {
		return nil, err
	}
	return buildDispatchResponse(statusCode, allJobsURL, runInfo), nil
}

// ResetGitHubOrganization handles POST /v1/github/reset-org.
func ResetGitHubOrganization(ctx context.Context, input *types.ResetGitHubOrganizationRequest) (*types.WorkflowDispatchResponse, error) {
	statusCode, allJobsURL, runInfo, err := github.ResetTenantGitHubOrganization(
		ctx,
		input.Body.CaptainDomain,
		input.Body.DeleteAllExistingRepos,
		input.Body.CustomDomain,
		input.Body.EnableCustomDomain,
	)
	if err != nil {
		return nil, err
	}
	return buildDispatchResponse(statusCode, allJobsURL, runInfo), nil
}

// GetWorkflowRunStatus handles GET /v1/github/workflow-status?run_url=...
func GetWorkflowRunStatus(ctx context.Context, input *types.GitHubWorkflowRunStatusRequest) (*types.WorkflowRunStatusResponse, error) {
	status, err := github.GetWorkflowRunStatus(ctx, input.RunURL)
	if err != nil {
		return nil, err
	}
	resp := &types.WorkflowRunStatusResponse{}
	resp.Body.RunID = status.RunID
	resp.Body.Name = status.Name
	resp.Body.Status = status.Status
	resp.Body.Conclusion = status.Conclusion
	resp.Body.RunURL = status.RunURL
	resp.Body.CreatedAt = status.CreatedAt
	resp.Body.UpdatedAt = status.UpdatedAt
	return resp, nil
}

func buildDispatchResponse(statusCode int, allJobsURL string, runInfo *github.RunInfo) *types.WorkflowDispatchResponse {
	resp := &types.WorkflowDispatchResponse{}
	resp.Body.StatusCode = statusCode
	resp.Body.AllJobsURL = allJobsURL
	resp.Body.RunID = runInfo.RunID
	resp.Body.RunURL = runInfo.RunURL
	return resp
}
