#!/usr/bin/env bash
# doctor.sh — why the bench page is not on her phone.
#
# She opened http://aegis:8791/ and got a black rectangle. The cause was two faults
# stacked: bench/ledgers/ was not in the checkout, so systemd refused to start a unit
# whose ReadWritePaths= named it (226/NAMESPACE); and the page drew itself in
# JavaScript, so even a running server had nothing to show if the first fetch failed.
# Both are fixed. This is so the next one takes thirty seconds to find instead of a
# night: it checks every link in the chain in order and prints the URL to open.
#
#     bash ~/repos/vintos/bench/doctor.sh
set -u

BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${BENCH_PORT:-8791}"
TOKEN_FILE="$HOME/.vintos/.bench-token"
BAD=0

say()  { printf '%s\n' "$*"; }
ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  BAD   %s\n' "$*"; BAD=1; }
fix()  { printf '        fix: %s\n' "$*"; }

say "== the checkout =="
if [ -d "$BENCH/ledgers" ]; then
  ok "bench/ledgers exists"
  if [ -w "$BENCH/ledgers" ]; then ok "and is writable"
  else bad "bench/ledgers is not writable"; fix "chmod u+w $BENCH/ledgers"; fi
else
  bad "bench/ledgers is MISSING — the unit will not start (226/NAMESPACE)"
  fix "cd ~/repos/vintos && git pull   # it is tracked now"
fi
[ -f "$BENCH/server.py" ] && ok "server.py present" || bad "server.py missing — pull"
[ -d "$BENCH/agents" ]    && ok "agents/ present"   || bad "agents/ missing — pull"

say ""
say "== the unit =="
UNIT=vintos-bench
if systemctl --user cat "$UNIT" >/dev/null 2>&1; then
  ok "$UNIT is installed"
  STATE=$(systemctl --user is-active "$UNIT" 2>/dev/null)
  if [ "$STATE" = "active" ]; then ok "and active"
  else
    bad "$UNIT is $STATE"
    systemctl --user status "$UNIT" --no-pager -l 2>&1 | sed -n '1,20p' | sed 's/^/        /'
    fix "systemctl --user restart $UNIT   # then read the lines above"
  fi
else
  bad "$UNIT is not installed"
  fix "cp ~/repos/vintos/broker/vintos-bench.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now $UNIT"
fi

say ""
say "== the port =="
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  ok "something is listening on $PORT"
elif command -v curl >/dev/null 2>&1 && curl -fsS --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  ok "$PORT answers /health"
else
  bad "nothing is listening on $PORT"
  fix "systemctl --user restart $UNIT, or run it in the foreground to see the error:"
  fix "python3 $BENCH/server.py"
fi

if command -v curl >/dev/null 2>&1; then
  H=$(curl -fsS --max-time 3 "http://127.0.0.1:$PORT/health" 2>/dev/null)
  case "$H" in *'"ok"'*) ok "/health says ok" ;; *) bad "/health did not answer" ;; esac
fi

say ""
say "== what the server sees =="
if command -v curl >/dev/null 2>&1; then
  T=""
  [ -f "$TOKEN_FILE" ] && T="?t=$(tr -d '\n' < "$TOKEN_FILE")"
  # Captured, not piped: a pipeline's status is sed's, and this must be able to fail.
  if D=$(curl -fsS --max-time 3 "http://127.0.0.1:$PORT/diag$T" 2>/dev/null); then
    printf '%s\n' "$D" | sed 's/^/  /'
  else
    bad "/diag did not answer — the server is down, or up and refusing (token?)"
  fi
fi

say ""
say "== how to reach it =="
HOSTN=$(hostname 2>/dev/null)
TS=$(command -v tailscale >/dev/null 2>&1 && tailscale status --json 2>/dev/null \
     | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null)
SUFFIX=""
if [ -f "$TOKEN_FILE" ]; then
  SUFFIX="?t=$(tr -d '\n' < "$TOKEN_FILE")"
  say "  a token is set, so the URL must carry it:"
fi
say "  http://${HOSTN}:${PORT}/${SUFFIX}"
[ -n "${TS:-}" ] && say "  http://${TS}:${PORT}/${SUFFIX}     (works from the phone off the LAN)"
say ""
say "  On the phone, type the whole thing including http:// and :$PORT — Safari turns a"
say "  bare hostname into a search."

say ""
if [ "$BAD" = "0" ]; then say "Everything above is green. If the page is still blank, open /diag in the browser:"
                          say "  http://${HOSTN}:${PORT}/diag${SUFFIX}"
else say "Fix the BAD lines above, in order, then run this again."; fi
exit "$BAD"
