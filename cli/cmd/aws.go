package cmd

import (
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var awsCmd = &cobra.Command{
	Use:   "aws",
	Short: "AWS account operations",
}

var awsSetupCredentialsCmd = &cobra.Command{
	Use:   "setup-credentials",
	Short: spec.Summary("/v1/aws/credentials", "post", "Get admin credentials for an AWS sub-account"),
	Long:  spec.Description("/v1/aws/credentials", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		accountName, _ := cmd.Flags().GetString("account-name")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/aws/credentials", map[string]string{
			"aws_sub_account_name": accountName,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

var awsNukeAccountCmd = &cobra.Command{
	Use:   "nuke-account",
	Short: spec.Summary("/v1/aws/nuke", "post", "Nuke an AWS sub-account"),
	Long:  spec.Description("/v1/aws/nuke", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		accountName, _ := cmd.Flags().GetString("account-name")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/aws/nuke", map[string]string{
			"aws_sub_account_name": accountName,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	awsSetupCredentialsCmd.Flags().String("account-name", "", spec.FlagDesc("AWS sub-account name", "AwsCredentialsRequestBody", "aws_sub_account_name"))
	awsSetupCredentialsCmd.MarkFlagRequired("account-name")

	awsNukeAccountCmd.Flags().String("account-name", "", spec.FlagDesc("AWS sub-account name to nuke", "AwsNukeAccountRequestBody", "aws_sub_account_name"))
	awsNukeAccountCmd.MarkFlagRequired("account-name")

	awsCmd.AddCommand(awsSetupCredentialsCmd)
	awsCmd.AddCommand(awsNukeAccountCmd)
	rootCmd.AddCommand(awsCmd)
}
