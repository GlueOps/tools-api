package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"github.com/GlueOps/tools-api/cli/api"
)

// newClient creates an authenticated API client.
func newClient() (*api.Client, error) {
	token, err := GetAuthToken()
	if err != nil {
		return nil, err
	}

	client, err := api.NewClient(apiURL, api.WithRequestEditorFn(func(ctx context.Context, req *http.Request) error {
		req.Header.Set("Authorization", "Bearer "+token)
		return nil
	}))
	if err != nil {
		return nil, fmt.Errorf("failed to create API client: %w", err)
	}
	return client, nil
}

// handleResponse reads and prints the response body, returning an error for non-2xx status.
func handleResponse(resp *http.Response) error {
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response: %w", err)
	}

	output := prettyJSON(body)

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		fmt.Print(output)
		if len(output) > 0 && output[len(output)-1] != '\n' {
			fmt.Println()
		}
		return nil
	}

	return fmt.Errorf("API error (HTTP %d): %s", resp.StatusCode, output)
}

// prettyJSON attempts to pretty-print JSON. Returns the original string if it's not valid JSON.
func prettyJSON(data []byte) string {
	var buf bytes.Buffer
	if err := json.Indent(&buf, data, "", "  "); err != nil {
		return string(data)
	}
	return buf.String()
}
