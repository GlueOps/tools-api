package auth

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"

	"github.com/GlueOps/tools-api/cli/internal/config"
)

const tokenFile = "tokens.json"

// TokenData holds the persisted OAuth2 tokens.
type TokenData struct {
	AccessToken  string    `json:"access_token"`
	RefreshToken string    `json:"refresh_token"`
	IDToken      string    `json:"id_token,omitempty"`
	Expiry       time.Time `json:"expiry"`
}

func tokenPath() (string, error) {
	dir, err := config.Dir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, tokenFile), nil
}

// SaveToken writes token data to disk.
func SaveToken(t *TokenData) error {
	p, err := tokenPath()
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(t, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(p, data, 0600)
}

// LoadToken reads token data from disk.
func LoadToken() (*TokenData, error) {
	p, err := tokenPath()
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(p)
	if err != nil {
		return nil, err
	}
	var t TokenData
	if err := json.Unmarshal(data, &t); err != nil {
		return nil, err
	}
	return &t, nil
}

// DeleteToken removes the token file.
func DeleteToken() error {
	p, err := tokenPath()
	if err != nil {
		return err
	}
	err = os.Remove(p)
	if os.IsNotExist(err) {
		return nil
	}
	return err
}

// IsValid returns true if the token exists and hasn't expired.
func (t *TokenData) IsValid() bool {
	return t.AccessToken != "" && time.Now().Before(t.Expiry)
}
