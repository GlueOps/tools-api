package hetzner

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"strings"

	"github.com/GlueOps/tools-api/pkg/chisel"
	"github.com/hetznercloud/hcloud-go/v2/hcloud"
)

const (
	imageName = "debian-12"
	location   = "hel1"
)

// newClient creates a Hetzner Cloud client. Reads HCLOUD_TOKEN lazily (risk C3).
func newClient() (*hcloud.Client, error) {
	token := os.Getenv("HCLOUD_TOKEN")
	if token == "" {
		return nil, fmt.Errorf("HCLOUD_TOKEN environment variable is not set")
	}
	return hcloud.NewClient(hcloud.WithToken(token)), nil
}

// buildCloudInit generates the cloud-init user data script that installs Docker
// and runs the Chisel server container with the given credentials.
func buildCloudInit(chiselCreds string) string {
	return fmt.Sprintf(`
#cloud-config
package_update: true
runcmd:
    - curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh && sudo apt install tmux -y
    - sudo docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 -it docker.io/jpillora/chisel:1 server --reverse --port=9090 --auth='%s'
`, chiselCreds)
}

// extractIPv4 returns the public IPv4 address string from a Hetzner server.
func extractIPv4(server *hcloud.Server) string {
	return server.PublicNet.IPv4.IP.String()
}

// DeleteExistingServers deletes all servers matching the given captain_domain label value.
func DeleteExistingServers(ctx context.Context, captainDomain string) error {
	captainDomain = strings.TrimSpace(captainDomain)
	slog.Info("starting deletion of existing chisel nodes", "captain_domain", captainDomain)

	client, err := newClient()
	if err != nil {
		return err
	}

	servers, err := client.Server.AllWithOpts(ctx, hcloud.ServerListOpts{
		ListOpts: hcloud.ListOpts{LabelSelector: "captain_domain"},
	})
	if err != nil {
		return fmt.Errorf("failed to fetch servers from Hetzner API: %w", err)
	}
	slog.Info("found servers with captain_domain label", "count", len(servers))

	deletedCount := 0
	for _, server := range servers {
		if server.Labels["captain_domain"] == captainDomain {
			slog.Info("deleting chisel node", "name", server.Name)
			_, _, err := client.Server.DeleteWithResult(ctx, server)
			if err != nil {
				return fmt.Errorf("failed to delete server %s: %w", server.Name, err)
			}
			slog.Info("successfully deleted chisel node", "name", server.Name)
			deletedCount++
		}
	}
	slog.Info("completed deletion of chisel nodes", "captain_domain", captainDomain, "deleted_count", deletedCount)
	return nil
}

// CreateInstances orchestrates chisel node creation: generates credentials,
// deletes existing servers, creates new ones with cloud-init, and returns the YAML manifest.
func CreateInstances(ctx context.Context, captainDomain string, nodeCount int) (string, error) {
	captainDomain = strings.TrimSpace(captainDomain)
	slog.Info("starting chisel node creation", "captain_domain", captainDomain)

	credentials, err := chisel.GenerateCredentials()
	if err != nil {
		return "", fmt.Errorf("failed to generate chisel credentials: %w", err)
	}
	slog.Info("successfully generated chisel credentials")

	userData := buildCloudInit(credentials)

	suffixes := chisel.GetSuffixes(nodeCount)
	slog.Info("got suffixes", "suffixes", suffixes, "node_count", nodeCount)

	instanceNames := make([]string, len(suffixes))
	for i, suffix := range suffixes {
		instanceNames[i] = fmt.Sprintf("%s-%s", captainDomain, suffix)
	}

	ipAddresses := make(map[string]string)

	if err := DeleteExistingServers(ctx, captainDomain); err != nil {
		return "", fmt.Errorf("error creating instances: %w", err)
	}

	client, err := newClient()
	if err != nil {
		return "", fmt.Errorf("error creating instances: %w", err)
	}

	for _, instanceName := range instanceNames {
		slog.Info("creating chisel node", "name", instanceName)
		ip, err := createServer(ctx, client, instanceName, captainDomain, userData)
		if err != nil {
			return "", fmt.Errorf("error creating instances: %w", err)
		}
		ipAddresses[instanceName] = ip
	}

	slog.Info("all chisel nodes created successfully", "ip_addresses", ipAddresses)

	yamlManifest := chisel.CreateChiselYAML(captainDomain, credentials, ipAddresses, suffixes)
	slog.Info("successfully generated chisel YAML manifest", "captain_domain", captainDomain)
	return yamlManifest, nil
}

// createServer creates a single Hetzner server with the given cloud-init user data.
func createServer(ctx context.Context, client *hcloud.Client, serverName, captainDomain, userData string) (string, error) {
	instanceType := os.Getenv("CHISEL_HCLOUD_INSTANCE_TYPE")
	slog.Info("creating instance", "type", instanceType, "name", serverName)

	result, _, err := client.Server.Create(ctx, hcloud.ServerCreateOpts{
		Name: serverName,
		ServerType: &hcloud.ServerType{
			Name: instanceType,
		},
		Image: &hcloud.Image{
			Name: imageName,
		},
		Location: &hcloud.Location{Name: location},
		UserData: userData,
		Labels: map[string]string{
			"captain_domain": captainDomain,
			"chisel_node":    "True",
		},
		PublicNet: &hcloud.ServerCreatePublicNet{
			EnableIPv4: true,
			EnableIPv6: false,
		},
	})
	if err != nil {
		return "", fmt.Errorf("failed to create server %s: %w", serverName, err)
	}
	slog.Info("Hetzner API call completed", "name", serverName)

	ipv4 := extractIPv4(result.Server)
	slog.Info("successfully created chisel node", "name", serverName, "ip", ipv4)
	return ipv4, nil
}
