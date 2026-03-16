package handlers

import (
	"context"

	"github.com/GlueOps/tools-api/pkg/opsgenie"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/GlueOps/tools-api/pkg/util"
)

// CreateOpsgenieManifest handles POST /v1/opsgenie/manifest.
// Returns plain text YAML manifest (risk C1).
func CreateOpsgenieManifest(ctx context.Context, input *types.OpsgenieAlertsManifestRequest) (*util.PlainTextResponse, error) {
	result := opsgenie.CreateOpsgenieAlertsManifest(input.Body.CaptainDomain, input.Body.OpsgenieAPIKey)
	return util.NewPlainTextResponse(result), nil
}
