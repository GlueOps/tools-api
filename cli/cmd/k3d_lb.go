package cmd

import (
	"context"

	"github.com/GlueOps/tools-api/cli/api"
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var k3dLbCmd = &cobra.Command{
	Use:   "k3d-lb-nodes",
	Short: "K3d load balancer node operations (Chisel on Proxmox via Waggle)",
}

var k3dLbCreateCmd = &cobra.Command{
	Use:   "create",
	Short: spec.Summary("/v1/k3d-lb-nodes", "post", "Create k3d-lb nodes"),
	Long:  spec.Description("/v1/k3d-lb-nodes", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		nodeCount, _ := cmd.Flags().GetInt("node-count")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.CreateK3dLbNodesV1K3dLbNodesPost(
			context.Background(),
			api.CreateK3dLbNodesV1K3dLbNodesPostJSONRequestBody{
				CaptainDomain: captainDomain,
				NodeCount:     &nodeCount,
			},
		)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

var k3dLbDeleteCmd = &cobra.Command{
	Use:   "delete",
	Short: spec.Summary("/v1/k3d-lb-nodes", "delete", "Delete k3d-lb nodes"),
	Long:  spec.Description("/v1/k3d-lb-nodes", "delete", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.DeleteK3dLbNodesV1K3dLbNodesDelete(
			context.Background(),
			api.DeleteK3dLbNodesV1K3dLbNodesDeleteJSONRequestBody{
				CaptainDomain: captainDomain,
			},
		)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	k3dLbCreateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "K3dLbNodesRequest", "captain_domain"))
	k3dLbCreateCmd.MarkFlagRequired("captain-domain")
	k3dLbCreateCmd.Flags().Int("node-count", 3, spec.FlagDesc("Number of exit nodes (1-6)", "K3dLbNodesRequest", "node_count"))

	k3dLbDeleteCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "K3dLbNodesDeleteRequest", "captain_domain"))
	k3dLbDeleteCmd.MarkFlagRequired("captain-domain")

	k3dLbCmd.AddCommand(k3dLbCreateCmd)
	k3dLbCmd.AddCommand(k3dLbDeleteCmd)
	rootCmd.AddCommand(k3dLbCmd)
}
