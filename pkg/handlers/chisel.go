package handlers

import (
	"context"

	"github.com/GlueOps/tools-api/pkg/hetzner"
	"github.com/GlueOps/tools-api/pkg/types"
	"github.com/GlueOps/tools-api/pkg/util"
)

// CreateChiselNodes handles POST /v1/chisel.
// Returns plain text YAML manifest (risk C1).
func CreateChiselNodes(ctx context.Context, input *types.ChiselNodesRequest) (*util.PlainTextResponse, error) {
	result, err := hetzner.CreateInstances(ctx, input.Body.CaptainDomain, input.Body.NodeCount)
	if err != nil {
		return nil, err
	}
	return util.NewPlainTextResponse(result), nil
}

// DeleteChiselNodes handles POST /v1/chisel/delete.
func DeleteChiselNodes(ctx context.Context, input *types.ChiselNodesDeleteRequest) (*types.MessageResponse, error) {
	if err := hetzner.DeleteExistingServers(ctx, input.Body.CaptainDomain); err != nil {
		return nil, err
	}
	resp := &types.MessageResponse{}
	resp.Body.Message = "Successfully deleted chisel nodes."
	return resp, nil
}
