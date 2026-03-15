package cmd

import (
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var chiselCmd = &cobra.Command{
	Use:   "chisel",
	Short: "Chisel load balancer node operations",
}

var chiselCreateCmd = &cobra.Command{
	Use:   "create",
	Short: spec.Summary("/v1/chisel", "post", "Create chisel nodes"),
	Long:  spec.Description("/v1/chisel", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		nodeCount, _ := cmd.Flags().GetInt("node-count")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/chisel", map[string]interface{}{
			"captain_domain": captainDomain,
			"node_count":     nodeCount,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

var chiselDeleteCmd = &cobra.Command{
	Use:   "delete",
	Short: spec.Summary("/v1/chisel/delete", "post", "Delete chisel nodes"),
	Long:  spec.Description("/v1/chisel/delete", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/chisel/delete", map[string]string{
			"captain_domain": captainDomain,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	chiselCreateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "ChiselNodesRequestBody", "captain_domain"))
	chiselCreateCmd.MarkFlagRequired("captain-domain")
	chiselCreateCmd.Flags().Int("node-count", 3, spec.FlagDesc("Number of exit nodes (1-6)", "ChiselNodesRequestBody", "node_count"))

	chiselDeleteCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "ChiselNodesDeleteRequestBody", "captain_domain"))
	chiselDeleteCmd.MarkFlagRequired("captain-domain")

	chiselCmd.AddCommand(chiselCreateCmd)
	chiselCmd.AddCommand(chiselDeleteCmd)
	rootCmd.AddCommand(chiselCmd)
}
