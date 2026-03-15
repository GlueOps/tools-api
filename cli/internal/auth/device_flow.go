package auth

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	DexIssuer = "https://dex.toolshosted.com"
	ClientID  = "tools-cli"
	Scopes    = "openid email profile offline_access"
)

type deviceCodeResponse struct {
	DeviceCode              string `json:"device_code"`
	UserCode                string `json:"user_code"`
	VerificationURI         string `json:"verification_uri"`
	VerificationURIComplete string `json:"verification_uri_complete"`
	ExpiresIn               int    `json:"expires_in"`
	Interval                int    `json:"interval"`
}

type tokenResponse struct {
	AccessToken  string `json:"access_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
	RefreshToken string `json:"refresh_token"`
	IDToken      string `json:"id_token"`
}

type tokenErrorResponse struct {
	Error string `json:"error"`
}

var httpClient = &http.Client{Timeout: 30 * time.Second}

func postForm(endpoint string, data url.Values) (*http.Response, error) {
	return httpClient.PostForm(endpoint, data)
}

// DeviceLogin performs the OAuth2 device code flow against Dex.
func DeviceLogin() (*TokenData, error) {
	deviceEndpoint := DexIssuer + "/device/code"
	tokenEndpoint := DexIssuer + "/token"

	// Step 1: Request device code
	resp, err := postForm(deviceEndpoint, url.Values{
		"client_id": {ClientID},
		"scope":     {Scopes},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to request device code: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read device code response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("device code request failed (HTTP %d): %s", resp.StatusCode, string(body))
	}

	var dcResp deviceCodeResponse
	if err := json.Unmarshal(body, &dcResp); err != nil {
		return nil, fmt.Errorf("failed to parse device code response: %w", err)
	}

	// Step 2: Display instructions
	fmt.Println()
	fmt.Println("To sign in, open this URL in a browser:")
	fmt.Println()
	if dcResp.VerificationURIComplete != "" {
		fmt.Printf("  %s\n", dcResp.VerificationURIComplete)
	} else {
		fmt.Printf("  %s\n", dcResp.VerificationURI)
		fmt.Printf("\n  and enter code: %s\n", dcResp.UserCode)
	}
	fmt.Println()
	fmt.Println("Waiting for authentication...")

	// Step 3: Poll for token
	interval := dcResp.Interval
	if interval < 5 {
		interval = 5
	}

	deadline := time.Now().Add(time.Duration(dcResp.ExpiresIn) * time.Second)
	for time.Now().Before(deadline) {
		time.Sleep(time.Duration(interval) * time.Second)

		tokenResp, err := postForm(tokenEndpoint, url.Values{
			"client_id":   {ClientID},
			"device_code": {dcResp.DeviceCode},
			"grant_type":  {"urn:ietf:params:oauth:grant-type:device_code"},
		})
		if err != nil {
			continue
		}

		tokenBody, err := io.ReadAll(tokenResp.Body)
		tokenResp.Body.Close()
		if err != nil {
			continue
		}

		if tokenResp.StatusCode == http.StatusOK {
			var tResp tokenResponse
			if err := json.Unmarshal(tokenBody, &tResp); err != nil {
				return nil, fmt.Errorf("failed to parse token response: %w", err)
			}
			td := &TokenData{
				AccessToken:  tResp.AccessToken,
				RefreshToken: tResp.RefreshToken,
				IDToken:      tResp.IDToken,
				Expiry:       time.Now().Add(time.Duration(tResp.ExpiresIn) * time.Second),
			}
			return td, nil
		}

		// Check for pending/slow_down
		var errResp tokenErrorResponse
		if err := json.Unmarshal(tokenBody, &errResp); err == nil {
			switch errResp.Error {
			case "authorization_pending":
				continue
			case "slow_down":
				interval += 5
				continue
			case "expired_token":
				return nil, fmt.Errorf("device code expired, please try again")
			case "access_denied":
				return nil, fmt.Errorf("access denied by user")
			default:
				return nil, fmt.Errorf("token error: %s", errResp.Error)
			}
		}
	}

	return nil, fmt.Errorf("authentication timed out")
}

// RefreshAccessToken uses the refresh token to get a new access token.
func RefreshAccessToken(refreshToken string) (*TokenData, error) {
	tokenEndpoint := DexIssuer + "/token"

	resp, err := postForm(tokenEndpoint, url.Values{
		"client_id":     {ClientID},
		"grant_type":    {"refresh_token"},
		"refresh_token": {refreshToken},
		"scope":         {Scopes},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to refresh token: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read refresh response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("token refresh failed (HTTP %d): %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var tResp tokenResponse
	if err := json.Unmarshal(body, &tResp); err != nil {
		return nil, fmt.Errorf("failed to parse refresh response: %w", err)
	}

	td := &TokenData{
		AccessToken:  tResp.AccessToken,
		RefreshToken: tResp.RefreshToken,
		IDToken:      tResp.IDToken,
		Expiry:       time.Now().Add(time.Duration(tResp.ExpiresIn) * time.Second),
	}
	return td, nil
}
