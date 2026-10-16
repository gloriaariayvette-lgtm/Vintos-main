#!/usr/bin/env bash
# Run as the owner on Aegis after deploying the broker. No secret is printed.
set -euo pipefail
action="${1:-grant}"
case "$action" in grant|revoke) ;; *) echo "usage: stratagem-charter.sh [grant|revoke]" >&2; exit 2;; esac
sudo -u atelier python3 /home/atelier/stratagem_store.py "$action"
mkdir -p "$HOME/.vintos/secrets"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 600 \
  /home/atelier/atelier/.stratagem-owner-key "$HOME/.vintos/secrets/stratagem-owner-token"
