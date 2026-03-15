package config

import (
	"os"
	"path/filepath"
)

// Dir returns the config directory path (~/.config/glueops/tools-cli/), creating it if needed.
func Dir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	dir := filepath.Join(home, ".config", "glueops", "tools-cli")
	if err := os.MkdirAll(dir, 0700); err != nil {
		return "", err
	}
	return dir, nil
}
