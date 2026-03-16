package handlers

import (
	"context"

	"github.com/GlueOps/tools-api/pkg/captain"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/GlueOps/tools-api/pkg/util"
)

// CreateCaptainManifests handles POST /v1/captain/manifests.
// Returns plain text YAML manifests (risk C1).
func CreateCaptainManifests(ctx context.Context, input *types.CaptainManifestsRequest) (*util.PlainTextResponse, error) {
	result := captain.GenerateManifests(
		input.Body.CaptainDomain,
		input.Body.TenantGitHubOrganizationName,
		input.Body.TenantDeploymentConfigurationsRepoName,
	)
	return util.NewPlainTextResponse(result), nil
}
