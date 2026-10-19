#!/bin/bash
# Starts the API. When TS_AUTHKEY is set, it first joins the tailnet with
# userspace-networking Tailscale and forwards 127.0.0.1:$PROXMOX_PORT to
# $PROXMOX_HOST:$PROXMOX_PORT (the Proxmox host's Tailscale IP), then points
# the API at 127.0.0.1, so the Proxmox client reaches Proxmox over Tailscale
# without any proxy configuration.
set -euo pipefail

if [ -z "${TS_AUTHKEY:-}" ]; then
    exec fastapi run
fi

if [ -z "${PROXMOX_HOST:-}" ]; then
    echo "ERROR: PROXMOX_HOST (the Proxmox host's Tailscale IP) is required when TS_AUTHKEY is set" >&2
    exit 1
fi

TS_HOSTNAME="${TS_HOSTNAME:-tools-api}"
PROXMOX_PORT="${PROXMOX_PORT:-8006}"
PROXMOX_TAILSCALE_HOST="$PROXMOX_HOST"

app_pid=""
tunnel_pids=()
# Stop the API first so in-flight requests can still reach Proxmox, then the tunnel.
shutdown() {
    if [ -n "$app_pid" ]; then
        kill -TERM "$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
    fi
    kill -TERM "${tunnel_pids[@]}" 2>/dev/null || true
    wait || true
}
trap 'shutdown; exit 0' TERM INT

echo "Starting tailscaled (userspace networking)..."
tailscaled --tun=userspace-networking --state=mem: &
tunnel_pids+=($!)

timeout=30
until tailscale status --json >/dev/null 2>&1; do
    sleep 1
    timeout=$((timeout - 1))
    if [ "$timeout" -eq 0 ]; then
        echo "ERROR: tailscaled failed to start within 30 seconds" >&2
        shutdown
        exit 1
    fi
done

echo "Connecting to Tailscale as $TS_HOSTNAME..."
# --shields-up: in userspace mode, inbound tailnet connections would otherwise be
# forwarded to this container's localhost (the API and the Proxmox forward).
# shellcheck disable=SC2086  # TS_EXTRA_ARGS is a list of flags
if ! tailscale up \
    --auth-key="$TS_AUTHKEY" \
    --hostname="$TS_HOSTNAME" \
    --accept-dns=false \
    --shields-up \
    --timeout=60s \
    ${TS_EXTRA_ARGS:-}; then
    echo "ERROR: failed to connect to Tailscale" >&2
    shutdown
    exit 1
fi
unset TS_AUTHKEY
echo "Connected to Tailscale as $(tailscale ip -4)"

echo "Forwarding 127.0.0.1:$PROXMOX_PORT to $PROXMOX_TAILSCALE_HOST:$PROXMOX_PORT over Tailscale..."
# socat logs every client-side connection close as an error; drop those lines.
socat "TCP-LISTEN:$PROXMOX_PORT,bind=127.0.0.1,fork,reuseaddr" \
    EXEC:"tailscale nc $PROXMOX_TAILSCALE_HOST $PROXMOX_PORT" \
    2> >(grep --line-buffered -v 'Connection reset by peer' >&2) &
tunnel_pids+=($!)

export PROXMOX_HOST=127.0.0.1
fastapi run &
app_pid=$!

# Exit as soon as any of tailscaled, socat or the API stops, so the container restarts.
status=0
wait -n "$app_pid" "${tunnel_pids[@]}" || status=$?
echo "A process exited (status $status), shutting down..." >&2
shutdown
exit $((status == 0 ? 1 : status))
