package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"os"
	"regexp"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// NewMinioClient initializes a MinIO client using environment variables.
// Reads MINIO_S3_ACCESS_KEY_ID, MINIO_S3_SECRET_KEY, HETZNER_STORAGE_REGION.
func NewMinioClient() (*minio.Client, error) {
	region := os.Getenv("HETZNER_STORAGE_REGION")
	accessKey := os.Getenv("MINIO_S3_ACCESS_KEY_ID")
	secretKey := os.Getenv("MINIO_S3_SECRET_KEY")

	if region == "" {
		return nil, fmt.Errorf("HETZNER_STORAGE_REGION environment variable is not set")
	}
	if accessKey == "" {
		return nil, fmt.Errorf("MINIO_S3_ACCESS_KEY_ID environment variable is not set")
	}
	if secretKey == "" {
		return nil, fmt.Errorf("MINIO_S3_SECRET_KEY environment variable is not set")
	}

	endpoint := fmt.Sprintf("%s.your-objectstorage.com", region)

	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: true,
		Region: region,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to initialize MinIO client: %w", err)
	}
	return client, nil
}

// SanitizeBucketName transforms a name to be S3-compliant: lowercase, strip
// invalid chars, strip leading/trailing hyphens, fallback to "default-name".
func SanitizeBucketName(name string) string {
	name = strings.ToLower(name)
	// Remove invalid characters (anything not lowercase letters, numbers, or hyphens).
	re := regexp.MustCompile(`[^a-z0-9\-]`)
	name = re.ReplaceAllString(name, "")
	// Strip leading hyphens.
	name = regexp.MustCompile(`^-+`).ReplaceAllString(name, "")
	// Strip trailing hyphens.
	name = regexp.MustCompile(`-+$`).ReplaceAllString(name, "")
	if name == "" {
		return "default-name"
	}
	return name
}

// StorageConfigs returns the parameterized storage configuration string for
// loki, thanos, and tempo. Reads env vars at call time (not at init time).
func StorageConfigs(bucketPrefix string) string {
	accessKey := os.Getenv("MINIO_S3_ACCESS_KEY_ID")
	secretKey := os.Getenv("MINIO_S3_SECRET_KEY")
	region := os.Getenv("HETZNER_STORAGE_REGION")

	lokiBucket := bucketPrefix + "-loki"
	thanosBucket := bucketPrefix + "-thanos"
	tempoBucket := bucketPrefix + "-tempo"

	return fmt.Sprintf(`
      loki_storage   = <<EOT
bucketNames:
        chunks: %s
        ruler: %s
        admin: %s
   type: s3
   s3:
      s3: %s
      endpoint: https://%s.your-objectstorage.com
      region: us-east-1
      accessKeyId: %s
      secretAccessKey: %s
      s3ForcePathStyle: false
      insecure: false
    EOT
      thanos_storage = <<EOT
type: s3
    config:
        bucket: %s
        endpoint: %s.your-objectstorage.com
        access_key: %s
        secret_key: %s
EOT
      tempo_storage  = <<EOT
backend: s3
    s3:
        access_key: %s
        secret_key: %s
        bucket:  %s
        endpoint: %s.your-objectstorage.com
        insecure: false
EOT
    `,
		lokiBucket, lokiBucket, lokiBucket, lokiBucket,
		region, accessKey, secretKey,
		thanosBucket, region, accessKey, secretKey,
		accessKey, secretKey, tempoBucket, region,
	)
}

// GenerateUniqueBucketName appends a 4-character hex suffix to the base name.
func GenerateUniqueBucketName(baseName string) (string, error) {
	b := make([]byte, 2)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("failed to generate random suffix: %w", err)
	}
	suffix := hex.EncodeToString(b)
	return fmt.Sprintf("%s-%s", baseName, suffix), nil
}

// ListBuckets returns all buckets from the MinIO server.
func ListBuckets(ctx context.Context, client *minio.Client) ([]minio.BucketInfo, error) {
	buckets, err := client.ListBuckets(ctx)
	if err != nil {
		return nil, fmt.Errorf("error listing buckets: %w", err)
	}
	return buckets, nil
}

// FindBucketsContaining returns bucket names that contain the base name.
func FindBucketsContaining(baseName string, buckets []minio.BucketInfo) []string {
	var matching []string
	for _, b := range buckets {
		if strings.Contains(b.Name, baseName) {
			matching = append(matching, b.Name)
		}
	}
	return matching
}

// DeleteAllObjects deletes all objects within the specified bucket using batch deletion.
func DeleteAllObjects(ctx context.Context, client *minio.Client, bucketName string) error {
	objectsCh := client.ListObjects(ctx, bucketName, minio.ListObjectsOptions{Recursive: true})

	removeObjectsCh := make(chan minio.ObjectInfo)
	go func() {
		defer close(removeObjectsCh)
		for obj := range objectsCh {
			if obj.Err != nil {
				slog.Error("error listing object", "bucket", bucketName, "error", obj.Err)
				continue
			}
			removeObjectsCh <- obj
		}
	}()

	for err := range client.RemoveObjects(ctx, bucketName, removeObjectsCh, minio.RemoveObjectsOptions{}) {
		slog.Error("failed to delete object", "bucket", bucketName, "object", err.ObjectName, "error", err.Err)
		return fmt.Errorf("error deleting object %q in bucket %q: %w", err.ObjectName, bucketName, err.Err)
	}
	return nil
}

// DeleteBucket removes the specified bucket. It does NOT delete objects first
// (matching Python behavior where delete_all_objects is commented out).
func DeleteBucket(ctx context.Context, client *minio.Client, bucketName string) error {
	if err := client.RemoveBucket(ctx, bucketName); err != nil {
		return fmt.Errorf("error removing bucket %q: %w", bucketName, err)
	}
	slog.Info("bucket deleted successfully", "bucket", bucketName)
	return nil
}

// CreateBuckets creates 3 sub-buckets with suffixes: tempo, loki, thanos.
func CreateBuckets(ctx context.Context, client *minio.Client, bucketName string) (string, error) {
	suffixes := []string{"tempo", "loki", "thanos"}
	for _, suffix := range suffixes {
		fullName := fmt.Sprintf("%s-%s", bucketName, suffix)
		if err := client.MakeBucket(ctx, fullName, minio.MakeBucketOptions{}); err != nil {
			return "", fmt.Errorf("error creating bucket %q: %w", fullName, err)
		}
		slog.Info("bucket created successfully", "bucket", fullName)
	}
	return bucketName, nil
}

// CreateAllBuckets is the main orchestrator: sanitize name, delete existing
// matching buckets, generate unique name, create new buckets, return config.
func CreateAllBuckets(ctx context.Context, captainDomain string) (string, error) {
	client, err := NewMinioClient()
	if err != nil {
		return "", err
	}

	slog.Info("listing all existing buckets")
	buckets, err := ListBuckets(ctx, client)
	if err != nil {
		return "", err
	}

	baseBucketName := SanitizeBucketName(captainDomain)
	matchingBuckets := FindBucketsContaining(baseBucketName, buckets)

	if len(matchingBuckets) > 0 {
		slog.Info("found matching buckets, deleting", "count", len(matchingBuckets), "baseName", baseBucketName)
		for _, name := range matchingBuckets {
			if err := DeleteBucket(ctx, client, name); err != nil {
				return "", err
			}
		}
	} else {
		slog.Info("no existing buckets contain the base name", "baseName", baseBucketName)
	}

	uniqueName, err := GenerateUniqueBucketName(baseBucketName)
	if err != nil {
		return "", err
	}
	slog.Info("generated unique bucket name", "name", uniqueName)

	bucketPrefix, err := CreateBuckets(ctx, client, uniqueName)
	if err != nil {
		return "", err
	}
	slog.Info("buckets created with prefix", "prefix", bucketPrefix)

	return StorageConfigs(bucketPrefix), nil
}
