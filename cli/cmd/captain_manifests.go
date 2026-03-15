package cmd

import (
	"context"

	"github.com/GlueOps/tools-api/cli/api"
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var captainManifestsCmd = &cobra.Command{
	Use:   "captain-manifests",
	Short: "Captain manifest operations",
}

var captainManifestsGenerateCmd = &cobra.Command{
	Use:   "generate",
	Short: spec.Summary("/v1/captain-manifests", "post", "Generate captain manifests"),
	Long:  spec.Description("/v1/captain-manifests", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		orgName, _ := cmd.Flags().GetString("org-name")
		repoName, _ := cmd.Flags().GetString("repo-name")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.CreateCaptainManifestsV1CaptainManifestsPost(
			context.Background(),
			api.CreateCaptainManifestsV1CaptainManifestsPostJSONRequestBody{
				CaptainDomain:                                captainDomain,
				TenantGithubOrganizationName:                 orgName,
				TenantDeploymentConfigurationsRepositoryName: repoName,
			},
		)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	captainManifestsGenerateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "CaptainManifestsRequest", "captain_domain"))
	captainManifestsGenerateCmd.MarkFlagRequired("captain-domain")
	captainManifestsGenerateCmd.Flags().String("org-name", "", spec.FlagDesc("Tenant GitHub organization name", "CaptainManifestsRequest", "tenant_github_organization_name"))
	captainManifestsGenerateCmd.MarkFlagRequired("org-name")
	captainManifestsGenerateCmd.Flags().String("repo-name", "", spec.FlagDesc("Deployment configurations repository name", "CaptainManifestsRequest", "tenant_deployment_configurations_repository_name"))
	captainManifestsGenerateCmd.MarkFlagRequired("repo-name")

	captainManifestsCmd.AddCommand(captainManifestsGenerateCmd)
	rootCmd.AddCommand(captainManifestsCmd)
}
