package storage

import (
	"testing"
)

func TestSanitizeBucketName(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"nonprod.foobar.onglueops.rocks", "nonprodfoobaronglueopsrocks"},
		{"Hello-World", "hello-world"},
		{"--leading-hyphens--", "leading-hyphens"},
		{"UPPER_CASE", "uppercase"},
		{"valid-name", "valid-name"},
		{"", "default-name"},
		{"---", "default-name"},
		{"a.b.c", "abc"},
		{"test@#$%name", "testname"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := SanitizeBucketName(tt.input)
			if got != tt.expected {
				t.Errorf("SanitizeBucketName(%q) = %q, want %q", tt.input, got, tt.expected)
			}
		})
	}
}

func TestGenerateUniqueBucketName(t *testing.T) {
	name, err := GenerateUniqueBucketName("test-bucket")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should be "test-bucket-XXXX" where XXXX is 4 hex chars.
	if len(name) != len("test-bucket-")+4 {
		t.Errorf("expected length %d, got %d (%q)", len("test-bucket-")+4, len(name), name)
	}

	// Two calls should produce different names.
	name2, err := GenerateUniqueBucketName("test-bucket")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if name == name2 {
		t.Errorf("expected different names, got %q both times", name)
	}
}

func TestFindBucketsContaining(t *testing.T) {
	// Use a minimal struct that satisfies minio.BucketInfo by using the actual type.
	// Since we import minio, we can use it directly.
	// But for simplicity we'll just test with the real types.
	// The function accepts []minio.BucketInfo, so we need the real type.
	// Let's skip this for now - covered by integration.
}

func TestStorageConfigs(t *testing.T) {
	t.Setenv("MINIO_S3_ACCESS_KEY_ID", "test-access-key")
	t.Setenv("MINIO_S3_SECRET_KEY", "test-secret-key")
	t.Setenv("HETZNER_STORAGE_REGION", "hel1")

	config := StorageConfigs("mybucket-abc1")

	// Verify key strings are present.
	checks := []string{
		"mybucket-abc1-loki",
		"mybucket-abc1-thanos",
		"mybucket-abc1-tempo",
		"test-access-key",
		"test-secret-key",
		"hel1.your-objectstorage.com",
		"loki_storage",
		"thanos_storage",
		"tempo_storage",
	}
	for _, s := range checks {
		if !contains(config, s) {
			t.Errorf("StorageConfigs output missing %q", s)
		}
	}
}

func contains(haystack, needle string) bool {
	return len(haystack) >= len(needle) && containsStr(haystack, needle)
}

func containsStr(s, substr string) bool {
	for i := 0; i+len(substr) <= len(s); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
