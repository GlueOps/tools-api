package cmd

import (
	"context"

	"github.com/GlueOps/tools-api/cli/api"
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var githubCmd = &cobra.Command{
	Use:   "github",
	Short: "GitHub organization operations",
}

var githubResetOrgCmd = &cobra.Command{
	Use:   "reset-org",
	Short: spec.Summary("/v1/reset-github-organization", "delete", "Reset a GitHub organization"),
	Long:  spec.Description("/v1/reset-github-organization", "delete", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		deleteAllRepos, _ := cmd.Flags().GetBool("delete-all-repos")
		customDomain, _ := cmd.Flags().GetString("custom-domain")
		enableCustomDomain, _ := cmd.Flags().GetBool("enable-custom-domain")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.ResetGithubOrganizationV1ResetGithubOrganizationDelete(
			context.Background(),
			api.ResetGithubOrganizationV1ResetGithubOrganizationDeleteJSONRequestBody{
				CaptainDomain:        captainDomain,
				DeleteAllExistingRepos: deleteAllRepos,
				CustomDomain:         customDomain,
				EnableCustomDomain:   enableCustomDomain,
			},
		)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

var githubWorkflowStatusCmd = &cobra.Command{
	Use:   "workflow-status",
	Short: spec.Summary("/v1/github/workflow-run-status", "post", "Get the status of a GitHub Actions workflow run"),
	Long:  spec.Description("/v1/github/workflow-run-status", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		runURL, _ := cmd.Flags().GetString("run-url")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.GetWorkflowRunStatusV1GithubWorkflowRunStatusPost(
			context.Background(),
			api.GetWorkflowRunStatusV1GithubWorkflowRunStatusPostJSONRequestBody{
				RunUrl: runURL,
			},
		)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	githubResetOrgCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "ResetGitHubOrganizationRequest", "captain_domain"))
	githubResetOrgCmd.MarkFlagRequired("captain-domain")
	githubResetOrgCmd.Flags().Bool("delete-all-repos", true, "Delete all existing repos")
	githubResetOrgCmd.Flags().String("custom-domain", "", spec.FlagDesc("Custom domain", "ResetGitHubOrganizationRequest", "custom_domain"))
	githubResetOrgCmd.Flags().Bool("enable-custom-domain", false, "Enable custom domain")

	githubWorkflowStatusCmd.Flags().String("run-url", "", spec.FlagDesc("GitHub Actions run URL", "GitHubWorkflowRunStatusRequest", "run_url"))
	githubWorkflowStatusCmd.MarkFlagRequired("run-url")

	githubCmd.AddCommand(githubResetOrgCmd)
	githubCmd.AddCommand(githubWorkflowStatusCmd)
	rootCmd.AddCommand(githubCmd)
}
