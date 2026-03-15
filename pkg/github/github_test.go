package github

import (
	"testing"
)

func TestPythonBool(t *testing.T) {
	if got := pythonBool(true); got != "True" {
		t.Errorf("pythonBool(true) = %q, want %q", got, "True")
	}
	if got := pythonBool(false); got != "False" {
		t.Errorf("pythonBool(false) = %q, want %q", got, "False")
	}
}

func TestRunURLPattern(t *testing.T) {
	tests := []struct {
		name      string
		url       string
		wantMatch bool
		wantOwner string
		wantRunID string
	}{
		{
			name:      "valid URL",
			url:       "https://github.com/internal-GlueOps/gha-tools-api/actions/runs/12345678",
			wantMatch: true,
			wantOwner: "internal-GlueOps/gha-tools-api",
			wantRunID: "12345678",
		},
		{
			name:      "valid URL different org",
			url:       "https://github.com/octocat/hello-world/actions/runs/99999",
			wantMatch: true,
			wantOwner: "octocat/hello-world",
			wantRunID: "99999",
		},
		{
			name:      "invalid - no run ID",
			url:       "https://github.com/owner/repo/actions/runs/",
			wantMatch: false,
		},
		{
			name:      "invalid - extra path segments (partial match prevented by $ anchor)",
			url:       "https://github.com/owner/repo/actions/runs/123/jobs",
			wantMatch: false,
		},
		{
			name:      "invalid - not github",
			url:       "https://gitlab.com/owner/repo/actions/runs/123",
			wantMatch: false,
		},
		{
			name:      "invalid - empty string",
			url:       "",
			wantMatch: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			match := runURLPattern.FindStringSubmatch(tt.url)
			if tt.wantMatch {
				if match == nil {
					t.Fatalf("expected match for %q, got nil", tt.url)
				}
				if match[1] != tt.wantOwner {
					t.Errorf("owner = %q, want %q", match[1], tt.wantOwner)
				}
				if match[2] != tt.wantRunID {
					t.Errorf("runID = %q, want %q", match[2], tt.wantRunID)
				}
			} else {
				if match != nil {
					t.Errorf("expected no match for %q, got %v", tt.url, match)
				}
			}
		})
	}
}

func TestHttpError(t *testing.T) {
	err := hError(400, "bad request")
	he, ok := err.(*httpError)
	if !ok {
		t.Fatal("expected *httpError")
	}
	if he.GetStatus() != 400 {
		t.Errorf("GetStatus() = %d, want 400", he.GetStatus())
	}
	if he.Error() != "bad request" {
		t.Errorf("Error() = %q, want %q", he.Error(), "bad request")
	}
}
