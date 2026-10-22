#!/usr/bin/env bash
# Cloud-session setup: join Gloria's tailnet as an ephemeral, tagged machine and make `ssh aegis` work.
# Runs as the cloud environment's setup script. Needs two environment secrets (never pasted into a chat):
#   TS_AUTHKEY          an ephemeral, tagged (tag:claude-agent), expiring Tailscale auth key
#   AEGIS_SSH_KEY_B64   the agent's own SSH private key, base64 on one line (the same key opens the Mac)
# and, to reach the Mac as well, two plain environment variables: MAC_TAILSCALE_IP and MAC_USER.
# The tailnet policy lets tag:claude-agent reach Aegis on port 22 and nothing else, and the key in Aegis's
# authorized_keys only works from the tailnet. Revoke either one in its admin page and this stops working.
set -euo pipefail
[ -n "${TS_AUTHKEY:-}" ] && [ -n "${AEGIS_SSH_KEY_B64:-}" ] || { echo "reach-aegis: secrets not set; skipping"; exit 0; }
TS=1.88.3
# Cloud containers come without an SSH client
command -v ssh >/dev/null || { apt-get install -y -qq openssh-client >/dev/null 2>&1 || \
  { apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq openssh-client >/dev/null 2>&1; }; }
D="$HOME/.local/tailscale"; mkdir -p "$D" "$HOME/.ssh"
if [ ! -x "$D/tailscaled" ]; then
  curl -fsSL "https://pkgs.tailscale.com/stable/tailscale_${TS}_amd64.tgz" | tar -xz -C "$D" --strip-components=1
fi
# Userspace networking: no root, no TUN device. State in memory: the machine leaves the tailnet when the session ends.
nohup "$D/tailscaled" --tun=userspace-networking --state=mem: --socket="$D/tailscaled.sock" \
      > "$D/tailscaled.log" 2>&1 &
for _ in $(seq 1 30); do "$D/tailscale" --socket="$D/tailscaled.sock" status >/dev/null 2>&1 && break || sleep 1; done
"$D/tailscale" --socket="$D/tailscaled.sock" up --authkey="$TS_AUTHKEY" --hostname="claude-agent-$(date +%m%d%H%M)" \
      --accept-routes=false --accept-dns=false
umask 077
printf '%s' "$AEGIS_SSH_KEY_B64" | base64 -d > "$HOME/.ssh/aegis_agent"
cat > "$HOME/.ssh/config" <<CFG
Host aegis
  HostName 100.72.225.119
  User gloria
  IdentityFile ~/.ssh/aegis_agent
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  ProxyCommand $D/tailscale --socket=$D/tailscaled.sock nc %h %p
CFG
if [ -n "${MAC_TAILSCALE_IP:-}" ] && [ -n "${MAC_USER:-}" ]; then
  cat >> "$HOME/.ssh/config" <<CFG
Host mac
  HostName $MAC_TAILSCALE_IP
  User $MAC_USER
  IdentityFile ~/.ssh/aegis_agent
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  ProxyCommand $D/tailscale --socket=$D/tailscaled.sock nc %h %p
CFG
fi
echo "reach-aegis: joined the tailnet; try: ssh aegis 'hostname; whoami'  (and ssh mac, if set)"
