package cmd

import (
	"github.com/GlueOps/tools-api/cli/internal/spec"
	"github.com/spf13/cobra"
)

var storageBucketsCmd = &cobra.Command{
	Use:   "storage-buckets",
	Short: "Manage storage buckets",
}

var storageBucketsCreateCmd = &cobra.Command{
	Use:   "create",
	Short: spec.Summary("/v1/storage/buckets", "post", "Create/re-create storage buckets"),
	Long:  spec.Description("/v1/storage/buckets", "post", ""),
	RunE: func(cmd *cobra.Command, args []string) error {
		captainDomain, _ := cmd.Flags().GetString("captain-domain")
		client, err := newClient()
		if err != nil {
			return err
		}
		resp, err := client.post("/v1/storage/buckets", map[string]string{
			"captain_domain": captainDomain,
		})
		if err != nil {
			return err
		}
		return handleResponse(resp)
	},
}

func init() {
	storageBucketsCreateCmd.Flags().String("captain-domain", "", spec.FlagDesc("Captain domain", "StorageBucketsRequestBody", "captain_domain"))
	storageBucketsCreateCmd.MarkFlagRequired("captain-domain")
	storageBucketsCmd.AddCommand(storageBucketsCreateCmd)
	rootCmd.AddCommand(storageBucketsCmd)
}
