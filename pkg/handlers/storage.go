package handlers

import (
	"context"
	"fmt"

	"github.com/GlueOps/tools-api/pkg/storage"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/GlueOps/tools-api/pkg/util"
)

// CreateStorageBuckets handles POST /v1/storage/buckets.
// Returns plain text storage configuration (risk C1).
func CreateStorageBuckets(ctx context.Context, input *types.StorageBucketsRequest) (*util.PlainTextResponse, error) {
	result, err := storage.CreateAllBuckets(ctx, input.Body.CaptainDomain)
	if err != nil {
		return nil, fmt.Errorf("failed to create storage buckets: %w", err)
	}
	return util.NewPlainTextResponse(result), nil
}
