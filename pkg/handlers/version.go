package handlers

import (
	"context"

	"github.com/GlueOps/tools-api/internal/version"
	"github.com/GlueOps/tools-api/pkg/types"
)

// VersionInput is an empty input for the version endpoint.
type VersionInput struct{}

// GetVersion returns version information injected at build time via ldflags.
func GetVersion(_ context.Context, _ *VersionInput) (*types.VersionResponse, error) {
	resp := &types.VersionResponse{}
	resp.Body.Version = version.Version
	resp.Body.CommitSHA = version.CommitSHA
	resp.Body.ShortSHA = version.ShortSHA
	resp.Body.BuildTimestamp = version.BuildTimestamp
	resp.Body.GitRef = version.GitRef
	return resp, nil
}
