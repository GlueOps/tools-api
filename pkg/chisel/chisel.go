package chisel

import (
	"crypto/rand"
	"fmt"
	"math/big"
	"strings"
)

const (
	credentialLength = 15
	charPool         = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

// GenerateCredentials generates a random username:password pair for Chisel authentication.
// Each part is 15 characters of alphanumeric characters, matching the Python implementation.
func GenerateCredentials() (string, error) {
	user, err := randomString(credentialLength)
	if err != nil {
		return "", fmt.Errorf("failed to generate credentials: %w", err)
	}
	pass, err := randomString(credentialLength)
	if err != nil {
		return "", fmt.Errorf("failed to generate credentials: %w", err)
	}
	return user + ":" + pass, nil
}

// GetSuffixes returns suffix names for the requested number of nodes (1-6).
func GetSuffixes(nodeCount int) []string {
	suffixes := make([]string, nodeCount)
	for i := 0; i < nodeCount; i++ {
		suffixes[i] = fmt.Sprintf("exit%d", i+1)
	}
	return suffixes
}

// CreateChiselYAML generates the kubectl manifest for Chisel operator resources.
func CreateChiselYAML(captainDomain, credentials string, ipAddresses map[string]string, suffixes []string) string {
	var b strings.Builder

	fmt.Fprintf(&b, `
kubectl apply -k https://github.com/FyraLabs/chisel-operator?ref=v0.7.1

kubectl apply -f - <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: selfhosted
  namespace: chisel-operator-system
type: Opaque
stringData:
  auth: "%s"
---
`, credentials)

	for _, suffix := range suffixes {
		key := fmt.Sprintf("%s-%s", captainDomain, suffix)
		fmt.Fprintf(&b, `apiVersion: chisel-operator.io/v1
kind: ExitNode
metadata:
  name: %s
  namespace: chisel-operator-system
spec:
  host: "%s"
  port: 9090
  auth: selfhosted
  chisel_image: docker.io/jpillora/chisel:1
---
`, suffix, ipAddresses[key])
	}

	b.WriteString("\nYAML\n")
	return b.String()
}

func randomString(length int) (string, error) {
	poolLen := big.NewInt(int64(len(charPool)))
	result := make([]byte, length)
	for i := 0; i < length; i++ {
		n, err := rand.Int(rand.Reader, poolLen)
		if err != nil {
			return "", err
		}
		result[i] = charPool[n.Int64()]
	}
	return string(result), nil
}
