package cmd

import (
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var captainManifestsCmd = &cobra.Command{
	Use:   "captain-manifests",
	Short: "Captain manifest operations",
}

var captainManifestsGenerateCmd = &cobra.Command{
	Use:   "generate",
	Short: spec.Summary("/v1/captain/manifests", "post", "Generate captain manifests"),
	Long:  spec.Description("/v1/captain/manifests", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		orgName, _ := cmd.Flags().GetString("org-name")
		repoName, _ := cmd.Flags().GetString("repo-name")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/captain/manifests", map[string]string{
			"captain_domain":                                  captainDomain,
			"tenant_github_organization_name":                 orgName,
			"tenant_deployment_configurations_repository_name": repoName,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	captainManifestsGenerateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "CaptainManifestsRequestBody", "captain_domain"))
	captainManifestsGenerateCmd.MarkFlagRequired("captain-domain")
	captainManifestsGenerateCmd.Flags().String("org-name", "", spec.FlagDesc("Tenant GitHub organization name", "CaptainManifestsRequestBody", "tenant_github_organization_name"))
	captainManifestsGenerateCmd.MarkFlagRequired("org-name")
	captainManifestsGenerateCmd.Flags().String("repo-name", "", spec.FlagDesc("Deployment configurations repository name", "CaptainManifestsRequestBody", "tenant_deployment_configurations_repository_name"))
	captainManifestsGenerateCmd.MarkFlagRequired("repo-name")

	captainManifestsCmd.AddCommand(captainManifestsGenerateCmd)
	rootCmd.AddCommand(captainManifestsCmd)
}
