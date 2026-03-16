package handlers

import (
	"context"

	"github.com/GlueOps/tools-api/pkg/types"
)

// HealthInput is an empty input for the health endpoint.
type HealthInput struct{}

// GetHealth returns a simple health check response.
func GetHealth(_ context.Context, _ *HealthInput) (*types.HealthResponse, error) {
	resp := &types.HealthResponse{}
	resp.Body.Status = "healthy"
	return resp, nil
}
