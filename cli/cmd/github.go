package cmd

import (
	"net/url"

	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var githubCmd = &cobra.Command{
	Use:   "github",
	Short: "GitHub organization operations",
}

var githubResetOrgCmd = &cobra.Command{
	Use:   "reset-org",
	Short: spec.Summary("/v1/github/reset-org", "post", "Reset a GitHub organization"),
	Long:  spec.Description("/v1/github/reset-org", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		deleteAllRepos, _ := cmd.Flags().GetBool("delete-all-repos")
		customDomain, _ := cmd.Flags().GetString("custom-domain")
		enableCustomDomain, _ := cmd.Flags().GetBool("enable-custom-domain")

		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/github/reset-org", map[string]interface{}{
			"captain_domain":           captainDomain,
			"delete_all_existing_repos": deleteAllRepos,
			"custom_domain":            customDomain,
			"enable_custom_domain":     enableCustomDomain,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

var githubWorkflowStatusCmd = &cobra.Command{
	Use:   "workflow-status",
	Short: spec.Summary("/v1/github/workflow-status", "get", "Get the status of a GitHub Actions workflow run"),
	Long:  spec.Description("/v1/github/workflow-status", "get", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		runURL, _ := cmd.Flags().GetString("run-url")
		client, err := newClient()
		if err != nil {
			return err
		}
		params := url.Values{}
		params.Set("run_url", runURL)
		resp, err := client.get("/v1/github/workflow-status", params)
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	githubResetOrgCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "ResetGitHubOrganizationRequestBody", "captain_domain"))
	githubResetOrgCmd.MarkFlagRequired("captain-domain")
	githubResetOrgCmd.Flags().Bool("delete-all-repos", true, "Delete all existing repos")
	githubResetOrgCmd.Flags().String("custom-domain", "", spec.FlagDesc("Custom domain", "ResetGitHubOrganizationRequestBody", "custom_domain"))
	githubResetOrgCmd.Flags().Bool("enable-custom-domain", false, "Enable custom domain")

	githubWorkflowStatusCmd.Flags().String("run-url", "", spec.FlagDesc("GitHub Actions run URL", "GitHubWorkflowRunStatusRequest", "run_url"))
	githubWorkflowStatusCmd.MarkFlagRequired("run-url")

	githubCmd.AddCommand(githubResetOrgCmd)
	githubCmd.AddCommand(githubWorkflowStatusCmd)
	rootCmd.AddCommand(githubCmd)
}
