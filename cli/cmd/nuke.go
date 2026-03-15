package cmd

import (
	"context"

	"github.com/GlueOps/tools-api/cli/api"
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var nukeCmd = &cobra.Command{
	Use:   "nuke",
	Short: "Nuke operations",
}

var nukeCaptainDomainDataCmd = &cobra.Command{
	Use:   "captain-domain-data",
	Short: spec.Summary("/v1/nuke-captain-domain-data", "delete", "Delete all backups/data for a captain domain"),
	Long:  spec.Description("/v1/nuke-captain-domain-data", "delete", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.NukeCaptainDomainDataV1NukeCaptainDomainDataDelete(
			context.Background(),
			api.NukeCaptainDomainDataV1NukeCaptainDomainDataDeleteJSONRequestBody{
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
	nukeCaptainDomainDataCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain to nuke", "CaptainDomainNukeDataAndBackupsRequest", "captain_domain"))
	nukeCaptainDomainDataCmd.MarkFlagRequired("captain-domain")
	nukeCmd.AddCommand(nukeCaptainDomainDataCmd)
	rootCmd.AddCommand(nukeCmd)
}
