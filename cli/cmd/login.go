package cmd

import (
	"fmt"

	"github.com/GlueOps/tools-api/cli/internal/auth"
	"github.com/spf13/cobra"
)

var loginCmd = &cobra.Command{
	Use:   "login",
	Short: "Authenticate with the Tools API via device code flow",
	RunE: func(cmd *cobra.Command, args []string) error {
		token, err := auth.DeviceLogin()
		if err != nil {
			return fmt.Errorf("login failed: %w", err)
		}

		if err := auth.SaveToken(token); err != nil {
			return fmt.Errorf("failed to save token: %w", err)
		}

		fmt.Println("Login successful!")
		return nil
	},
}

func init() {
	rootCmd.AddCommand(loginCmd)
}
