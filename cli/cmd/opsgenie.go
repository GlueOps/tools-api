package cmd

import (
	"context"

	"github.com/GlueOps/tools-api/cli/api"
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var opsgenieCmd = &cobra.Command{
	Use:   "opsgenie",
	Short: "Opsgenie operations",
}

var opsgenieCreateCmd = &cobra.Command{
	Use:   "create",
	Short: spec.Summary("/v1/opsgenie", "post", "Create Opsgenie alerts manifest"),
	Long:  spec.Description("/v1/opsgenie", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		apiKey, _ := cmd.Flags().GetString("api-key")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.CreateOpsgeniealertsManifestV1OpsgeniePost(
			context.Background(),
			api.CreateOpsgeniealertsManifestV1OpsgeniePostJSONRequestBody{
				CaptainDomain: captainDomain,
				OpsgenieApiKey: apiKey,
			},
		)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	opsgenieCreateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "OpsgenieAlertsManifestRequest", "captain_domain"))
	opsgenieCreateCmd.MarkFlagRequired("captain-domain")
	opsgenieCreateCmd.Flags().String("api-key", "", spec.FlagDesc("Opsgenie API key", "OpsgenieAlertsManifestRequest", "opsgenie_api_key"))
	opsgenieCreateCmd.MarkFlagRequired("api-key")

	opsgenieCmd.AddCommand(opsgenieCreateCmd)
	rootCmd.AddCommand(opsgenieCmd)
}
