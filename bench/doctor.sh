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
INSTALLED=0
if systemctl --user cat "$UNIT" >/dev/null 2>&1; then
  INSTALLED=1
  ok "$UNIT is installed"
  # Type=simple marks a unit active the instant the process is spawned. "active" one
  # second after a restart says nothing about whether it survived. So: look again a
  # moment later, and believe the restart counter over the word.
  STATE=$(systemctl --user is-active "$UNIT" 2>/dev/null)
  sleep 2
  STATE2=$(systemctl --user is-active "$UNIT" 2>/dev/null)
  N=$(systemctl --user show -p NRestarts --value "$UNIT" 2>/dev/null)
  if [ "$STATE2" = "active" ] && [ "$STATE" = "active" ]; then
    ok "and still active two seconds later"
  else
    bad "$UNIT is $STATE2 (was $STATE)"
  fi
  [ "${N:-0}" -gt 2 ] 2>/dev/null && bad "it has restarted ${N} times — it is crash-looping, not running"
else
  bad "$UNIT is not installed"
  fix "cp ~/repos/vintos/broker/vintos-bench.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now $UNIT"
fi

say ""
say "== the port =="
LIVE=0
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  ok "something is listening on $PORT"; LIVE=1
elif command -v curl >/dev/null 2>&1 && curl -fsS --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  ok "$PORT answers /health"; LIVE=1
else
  bad "nothing is listening on $PORT"
fi

if [ "$LIVE" = "1" ] && command -v curl >/dev/null 2>&1; then
  H=$(curl -fsS --max-time 3 "http://127.0.0.1:$PORT/health" 2>/dev/null)
  case "$H" in *'"ok"'*) ok "/health says ok" ;; *) bad "/health did not answer" ;; esac
fi

# A dead port with no reason printed is what sent her back to a black page. Whatever
# is wrong, the reason is in one of these two places, so print BOTH without being
# asked: what systemd logged, and what the code does outside systemd's sandbox.
if [ "$LIVE" = "0" ]; then
  say ""
  say "== why the port is dead =="
  if [ "$INSTALLED" = "1" ]; then
    say "  -- what systemd logged --"
    journalctl --user -u "$UNIT" -n 40 --no-pager 2>/dev/null | sed 's/^/  /' \
      || say "  (no journal — try: systemctl --user status $UNIT -l)"
    say ""
    say "  -- how it exited --"
    systemctl --user show "$UNIT" \
      -p Result -p ExecMainStatus -p ExecMainCode -p NRestarts -p StatusErrno 2>/dev/null \
      | sed 's/^/  /'
    say ""
    say "  Result=exit-code with ExecMainStatus=1 is the code throwing — read the journal above."
    say "  Result=exit-code with ExecMainStatus=226 (NAMESPACE) is the sandbox: a path in"
    say "  ReadWritePaths=/ProtectSystem= that systemd could not set up. Nothing reached python."
  fi
  say ""
  say "  -- the same code, outside the sandbox, on a scratch port --"
  # If this serves and the unit does not, the code is fine and the unit is the problem.
  SCRATCH=8799
  ( BENCH_PORT="$SCRATCH" timeout 3 python3 "$BENCH/server.py" 2>&1 | head -20 | sed 's/^/  /' ) \
    || true
  say ""
  if command -v curl >/dev/null 2>&1; then
    ( BENCH_PORT="$SCRATCH" python3 "$BENCH/server.py" >/dev/null 2>&1 & echo $! > /tmp/.bench-probe ) 
    sleep 1.5
    if curl -fsS --max-time 3 "http://127.0.0.1:$SCRATCH/health" >/dev/null 2>&1; then
      if [ "$INSTALLED" = "1" ]; then
        say "  VERDICT: the code serves fine on its own. The unit's sandbox is what is stopping it."
        fix "systemctl --user edit $UNIT   # and comment out ProtectSystem/ProtectHome to confirm"
      else
        say "  VERDICT: the code serves fine on its own. Nothing is wrong with it — the unit"
        say "           is simply not installed. Run the fix above."
      fi
    else
      say "  VERDICT: the code does not serve even outside systemd. The error is in the lines above."
    fi
    kill "$(cat /tmp/.bench-probe 2>/dev/null)" 2>/dev/null
    rm -f /tmp/.bench-probe
  fi
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
HOSTN=$(hostname 2>/dev/null | tr "A-Z" "a-z")
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
