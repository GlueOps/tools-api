package captain

import (
	"strings"
	"testing"
)

func TestExtractEnvironmentName(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"nonprod.foobar.onglueops.rocks", "nonprod"},
		{"prod.example.com", "prod"},
		{"staging", "staging"},
	}
	for _, tc := range tests {
		got := extractEnvironmentName(tc.input)
		if got != tc.want {
			t.Errorf("extractEnvironmentName(%q) = %q, want %q", tc.input, got, tc.want)
		}
	}
}

func TestGenerateManifests(t *testing.T) {
	result := GenerateManifests(
		"nonprod.antoniostaqueria.onglueops.com",
		"dev-tenant",
		"deployment-configurations",
	)

	// Should contain 3 YAML documents separated by ---
	docs := strings.Split(result, "\n---\n")
	if len(docs) != 3 {
		t.Fatalf("expected 3 YAML documents, got %d", len(docs))
	}

	// Namespace document
	if !strings.Contains(docs[0], "kind: Namespace") {
		t.Error("first document should be a Namespace")
	}
	if !strings.Contains(docs[0], "name: nonprod") {
		t.Error("namespace should use environment name 'nonprod'")
	}

	// AppProject document
	if !strings.Contains(docs[1], "kind: AppProject") {
		t.Error("second document should be an AppProject")
	}
	if !strings.Contains(docs[1], "dev-tenant") {
		t.Error("appproject should contain tenant org name")
	}
	if !strings.Contains(docs[1], "deployment-configurations") {
		t.Error("appproject should contain tenant repo name")
	}

	// ApplicationSet document
	if !strings.Contains(docs[2], "kind: ApplicationSet") {
		t.Error("third document should be an ApplicationSet")
	}
	if !strings.Contains(docs[2], "captain_domain: nonprod.antoniostaqueria.onglueops.com") {
		t.Error("appset should contain full captain_domain")
	}

	// Go template syntax in output must be preserved literally
	if !strings.Contains(docs[2], `{{ index .path.segments 1 | replace "." "-"  | replace "_" "-" }}`) {
		t.Error("Go template syntax in appset output must be preserved")
	}

	// No unresolved placeholders
	if strings.Contains(result, "<%") || strings.Contains(result, "%>") {
		t.Error("output should not contain unresolved template placeholders")
	}
}
