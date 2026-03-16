package cmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// apiClient is a simple HTTP client wrapper for the Tools API.
type apiClient struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

// newClient creates an authenticated API client.
func newClient() (*apiClient, error) {
	token, err := GetAuthToken()
	if err != nil {
		return nil, err
	}
	return &apiClient{
		baseURL:    apiURL,
		token:      token,
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}, nil
}

// post sends a POST request with a JSON body.
func (c *apiClient) post(path string, body interface{}) (*http.Response, error) {
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request body: %w", err)
	}
	req, err := http.NewRequest(http.MethodPost, c.baseURL+path, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.token)
	return c.httpClient.Do(req)
}

// get sends a GET request with optional query parameters.
func (c *apiClient) get(path string, params url.Values) (*http.Response, error) {
	u := c.baseURL + path
	if len(params) > 0 {
		u += "?" + params.Encode()
	}
	req, err := http.NewRequest(http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	return c.httpClient.Do(req)
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
