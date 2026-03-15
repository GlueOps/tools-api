package handlers

import (
	"context"

	awsmod "github.com/GlueOps/tools-api/pkg/aws"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/GlueOps/tools-api/pkg/util"
)

// CreateAwsCredentials handles POST /v1/aws/credentials.
// Returns plain text .env configuration (risk C1).
func CreateAwsCredentials(ctx context.Context, input *types.AwsCredentialsRequest) (*util.PlainTextResponse, error) {
	result, err := awsmod.CreateAdminCredentialsWithinCaptainAccount(ctx, input.Body.AwsSubAccountName)
	if err != nil {
		return nil, err
	}
	return util.NewPlainTextResponse(result), nil
}
