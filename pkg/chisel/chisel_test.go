package chisel

import (
	"strings"
	"testing"
	"unicode"
)

func TestGenerateCredentials(t *testing.T) {
	creds, err := GenerateCredentials()
	if err != nil {
		t.Fatalf("GenerateCredentials() returned error: %v", err)
	}

	parts := strings.SplitN(creds, ":", 2)
	if len(parts) != 2 {
		t.Fatalf("expected username:password format, got %q", creds)
	}

	for i, part := range parts {
		label := "username"
		if i == 1 {
			label = "password"
		}

		if len(part) != 15 {
			t.Errorf("%s length = %d, want 15", label, len(part))
		}

		for _, ch := range part {
			if !unicode.IsLetter(ch) && !unicode.IsDigit(ch) {
				t.Errorf("%s contains non-alphanumeric character: %c", label, ch)
			}
		}
	}

	// Verify uniqueness (probabilistic but extremely unlikely to fail)
	creds2, err := GenerateCredentials()
	if err != nil {
		t.Fatalf("second GenerateCredentials() returned error: %v", err)
	}
	if creds == creds2 {
		t.Error("two consecutive credential generations produced identical results")
	}
}

func TestGetSuffixes(t *testing.T) {
	tests := []struct {
		count int
		want  []string
	}{
		{1, []string{"exit1"}},
		{3, []string{"exit1", "exit2", "exit3"}},
		{6, []string{"exit1", "exit2", "exit3", "exit4", "exit5", "exit6"}},
	}

	for _, tt := range tests {
		got := GetSuffixes(tt.count)
		if len(got) != len(tt.want) {
			t.Errorf("GetSuffixes(%d) returned %d items, want %d", tt.count, len(got), len(tt.want))
			continue
		}
		for i := range got {
			if got[i] != tt.want[i] {
				t.Errorf("GetSuffixes(%d)[%d] = %q, want %q", tt.count, i, got[i], tt.want[i])
			}
		}
	}
}

func TestCreateChiselYAML(t *testing.T) {
	captainDomain := "nonprod.foobar.onglueops.rocks"
	credentials := "testuser1234567:testpass1234567"
	ipAddresses := map[string]string{
		"nonprod.foobar.onglueops.rocks-exit1": "1.2.3.4",
		"nonprod.foobar.onglueops.rocks-exit2": "5.6.7.8",
	}
	suffixes := []string{"exit1", "exit2"}

	result := CreateChiselYAML(captainDomain, credentials, ipAddresses, suffixes)

	// Verify key elements are present
	checks := []string{
		"kubectl apply -k https://github.com/FyraLabs/chisel-operator?ref=v0.7.1",
		"kubectl apply -f - <<YAML",
		`auth: "testuser1234567:testpass1234567"`,
		"name: selfhosted",
		"namespace: chisel-operator-system",
		"apiVersion: chisel-operator.io/v1",
		"kind: ExitNode",
		"name: exit1",
		"name: exit2",
		`host: "1.2.3.4"`,
		`host: "5.6.7.8"`,
		"port: 9090",
		"auth: selfhosted",
		"chisel_image: docker.io/jpillora/chisel:1",
		"YAML",
	}

	for _, check := range checks {
		if !strings.Contains(result, check) {
			t.Errorf("YAML manifest missing expected content: %q", check)
		}
	}

	// Verify ExitNode blocks appear for each suffix
	exitNodeCount := strings.Count(result, "kind: ExitNode")
	if exitNodeCount != 2 {
		t.Errorf("expected 2 ExitNode blocks, got %d", exitNodeCount)
	}
}
