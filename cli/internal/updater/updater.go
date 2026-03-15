package updater

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"runtime"
	"time"

	"github.com/GlueOps/tools-api/cli/internal/version"
)

type versionResponse struct {
	Version string `json:"version"`
}

// CheckAndUpdate checks the API version and self-updates if there's a mismatch.
// Returns true if an update was performed (caller should tell user to re-run).
func CheckAndUpdate(apiURL string) (bool, error) {
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(apiURL + "/version")
	if err != nil {
		return false, nil // silently skip if API unreachable
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, nil
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, nil
	}

	var vResp versionResponse
	if err := json.Unmarshal(body, &vResp); err != nil {
		return false, nil
	}

	if vResp.Version == "" || vResp.Version == "UNKNOWN" || vResp.Version == "dev" || vResp.Version == version.Version {
		return false, nil
	}

	fmt.Printf("Update available: %s -> %s\n", version.Version, vResp.Version)
	fmt.Println("Downloading update...")

	downloadURL := fmt.Sprintf(
		"https://github.com/GlueOps/tools-api/releases/download/%s/tools-%s-%s",
		vResp.Version, runtime.GOOS, runtime.GOARCH,
	)

	resp, err = client.Get(downloadURL)
	if err != nil {
		return false, fmt.Errorf("failed to download update: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("update download failed (HTTP %d)", resp.StatusCode)
	}

	execPath, err := os.Executable()
	if err != nil {
		return false, fmt.Errorf("cannot determine executable path: %w", err)
	}

	// Write to temp file next to the binary, then rename
	tmpPath := execPath + ".update"
	f, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0755)
	if err != nil {
		return false, fmt.Errorf("cannot create update file: %w", err)
	}

	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		os.Remove(tmpPath)
		return false, fmt.Errorf("failed to write update: %w", err)
	}
	if err := f.Sync(); err != nil {
		f.Close()
		os.Remove(tmpPath)
		return false, fmt.Errorf("failed to sync update file: %w", err)
	}
	f.Close()

	if err := os.Rename(tmpPath, execPath); err != nil {
		os.Remove(tmpPath)
		return false, fmt.Errorf("failed to replace binary: %w", err)
	}

	fmt.Printf("Updated to %s. Please re-run your command.\n", vResp.Version)
	return true, nil
}
