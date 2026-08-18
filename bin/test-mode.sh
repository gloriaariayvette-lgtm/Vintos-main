#!/bin/bash
FLAG="$HOME/.vintos/workspace/memory/.test-mode"
case "${1:-status}" in
  on)  touch "$FLAG"; echo "TEST MODE ON — conversations will NOT persist." ;;
  off) rm -f "$FLAG"; echo "TEST MODE OFF — everything keeps." ;;
  status) [ -f "$FLAG" ] && echo "TEST MODE ON (nothing persisting!)" || echo "test mode off — everything keeps" ;;
esac
