#!/usr/bin/env python3
"""Refresh the DoorDash access token on Aegis from the Mac stage — once a day, so Gloria never
has to do it by hand.

dd-cli's access token expires every few days; the Mac's keychain LOGIN lasts far longer, so the
Mac can mint a fresh access token on demand (`dd-cli export-token`). This asks the Mac stage's
secret-gated /dd-token for one over the tailnet and writes it to ~/.vintos/secrets/dd-cli.token
(0600), where food_order reads it. The token is never printed or logged.

Driven once a day by first-light.sh. Safe to run any time; a failure leaves the existing token in
place. Exit 0 on success or a clean skip, 1 on a real failure.
"""
import json
import os
import sys
import urllib.request

STAGE = os.environ.get("VINTOS_MAC_STAGE", "http://100.79.177.103:8511").rstrip("/")
SECRET = os.environ.get("VINTOS_STAGE_SECRET", "")
TOKEN_FILE = os.path.expanduser(os.environ.get("DD_CLI_TOKEN_FILE", "~/.vintos/secrets/dd-cli.token"))

# Tests replace this boundary so no suite reaches the Mac.
OPEN = urllib.request.urlopen


def fetch_token():
    req = urllib.request.Request(STAGE + "/dd-token", data=b"{}",
                                 headers={"Content-Type": "application/json",
                                          "X-Vintos-Stage-Secret": SECRET}, method="POST")
    with OPEN(req, timeout=180) as response:
        return json.loads(response.read())


def main():
    if not SECRET:
        print("[dd-token] VINTOS_STAGE_SECRET not set; nothing to do")
        return 0
    try:
        data = fetch_token()
    except Exception as exc:
        print("[dd-token] refresh failed:", str(exc)[:200])
        return 1
    token = str((data or {}).get("token") or "").strip()
    if not (data or {}).get("ok") or not token:
        print("[dd-token] no token returned:", str((data or {}).get("error"))[:200])
        return 1
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_FILE)
    try: os.chmod(TOKEN_FILE, 0o600)
    except OSError: pass
    print("[dd-token] refreshed (%d bytes)" % len(token))
    return 0


if __name__ == "__main__":
    sys.exit(main())
