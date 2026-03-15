package cmd

import (
	"fmt"

	"github.com/GlueOps/tools-api/cli/internal/version"
	"github.com/spf13/cobra"
)

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print version information",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("tools %s\n", version.Version)
		fmt.Printf("  commit:    %s\n", version.ShortSHA)
		fmt.Printf("  built:     %s\n", version.BuildTimestamp)
		fmt.Printf("  ref:       %s\n", version.GitRef)
	},
}

func init() {
	rootCmd.AddCommand(versionCmd)
}
