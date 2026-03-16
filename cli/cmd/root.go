package cmd

import (
	"fmt"

	"github.com/GlueOps/tools-api/cli/internal/auth"
	"github.com/spf13/cobra"
)

var apiURL string

// skipAuthCommands lists commands that don't require authentication.
var skipAuthCommands = map[string]bool{
	"login":      true,
	"logout":     true,
	"version":    true,
	"help":       true,
	"completion": true,
}

var rootCmd = &cobra.Command{
	Use:   "tools",
	Short: "GlueOps platform engineering CLI",
	Long:  "CLI for interacting with the GlueOps Tools API.",
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		// Skip for commands that don't need auth
		if !cmd.HasParent() || skipAuthCommands[cmd.Name()] {
			return nil
		}

		// Auth check
		token, err := auth.LoadToken()
		if err != nil {
			return fmt.Errorf("not logged in. Run 'tools login' first")
		}
		if !token.IsValid() {
			// Try refresh
			if token.RefreshToken != "" {
				newToken, err := auth.RefreshAccessToken(token.RefreshToken)
				if err == nil {
					if err := auth.SaveToken(newToken); err != nil {
						return fmt.Errorf("failed to save refreshed token: %w", err)
					}
					return nil
				}
			}
			return fmt.Errorf("token expired. Run 'tools login' to re-authenticate")
		}
		return nil
	},
	SilenceUsage: true,
}

func init() {
	rootCmd.PersistentFlags().StringVar(&apiURL, "api-url", "https://tools.toolshosted.rocks", "Tools API base URL")
}

// Execute runs the root command.
func Execute() error {
	return rootCmd.Execute()
}

// GetAPIURL returns the configured API URL.
func GetAPIURL() string {
	return apiURL
}

// GetAuthToken returns the current access token, refreshing if needed.
func GetAuthToken() (string, error) {
	token, err := auth.LoadToken()
	if err != nil {
		return "", fmt.Errorf("not logged in. Run 'tools login' first")
	}
	if !token.IsValid() && token.RefreshToken != "" {
		newToken, err := auth.RefreshAccessToken(token.RefreshToken)
		if err != nil {
			return "", fmt.Errorf("token expired, refresh failed: %w", err)
		}
		if err := auth.SaveToken(newToken); err != nil {
			return "", err
		}
		return newToken.AccessToken, nil
	}
	return token.AccessToken, nil
}
