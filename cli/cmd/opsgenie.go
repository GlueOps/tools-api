package cmd

import (
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var opsgenieCmd = &cobra.Command{
	Use:   "opsgenie",
	Short: "Opsgenie operations",
}

var opsgenieCreateCmd = &cobra.Command{
	Use:   "create",
	Short: spec.Summary("/v1/opsgenie/manifest", "post", "Create Opsgenie alerts manifest"),
	Long:  spec.Description("/v1/opsgenie/manifest", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		apiKey, _ := cmd.Flags().GetString("api-key")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/opsgenie/manifest", map[string]string{
			"captain_domain":  captainDomain,
			"opsgenie_api_key": apiKey,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	opsgenieCreateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "OpsgenieAlertsManifestRequestBody", "captain_domain"))
	opsgenieCreateCmd.MarkFlagRequired("captain-domain")
	opsgenieCreateCmd.Flags().String("api-key", "", spec.FlagDesc("Opsgenie API key", "OpsgenieAlertsManifestRequestBody", "opsgenie_api_key"))
	opsgenieCreateCmd.MarkFlagRequired("api-key")

	opsgenieCmd.AddCommand(opsgenieCreateCmd)
	rootCmd.AddCommand(opsgenieCmd)
}
