#!/usr/bin/env bash
# tailnet-window.sh — put the room window (loopback 127.0.0.1:$WEB_PORT) on the tailnet through `tailscale serve`:
# HTTPS, tailnet only, never Funnel. Sourced by setup-aegis.sh; prints the address to use as WINDOW_URL=... on its
# last line. Fails closed: with no Tailscale, no tailnet address or a refused serve, the window stays on this machine
# and the exact command to run by hand is printed. It never turns Funnel on and never touches another port.
tailnet_window() {
  local web_port="${1:-8788}" https_port="${2:-8789}" ts dns
  ts="$(command -v tailscale || true)"
  if [ -z "$ts" ]; then
    echo "tailnet window: Tailscale is not installed here; the window stays on this machine only"
    echo "WINDOW_URL=http://127.0.0.1:${web_port}"; return 0
  fi
  if [ -z "$("$ts" ip -4 2>/dev/null | head -1)" ]; then
    echo "tailnet window: Tailscale is not up (no tailnet address); the window stays on this machine only"
    echo "WINDOW_URL=http://127.0.0.1:${web_port}"; return 0
  fi
  dns="$("$ts" status --json 2>/dev/null | python3 -c 'import json,sys; print((json.load(sys.stdin).get("Self") or {}).get("DNSName","").rstrip("."))' 2>/dev/null)"
  if "$ts" serve --bg --https="${https_port}" "http://127.0.0.1:${web_port}" >/dev/null 2>&1 && [ -n "$dns" ]; then
    echo "tailnet window: served on the tailnet only (https ${https_port} -> 127.0.0.1:${web_port})"
    echo "WINDOW_URL=https://${dns}:${https_port}"; return 0
  fi
  echo "tailnet window: tailscale serve was refused here; the window stays on this machine only. To put it on the tailnet, run:"
  echo "  tailscale serve --bg --https=${https_port} http://127.0.0.1:${web_port}"
  echo "WINDOW_URL=http://127.0.0.1:${web_port}"; return 0
}
