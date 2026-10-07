#!/usr/bin/env python3
"""home_presence.py — is Gloria's phone on the house wifi?

Option 1 of the position ladder, chosen by her: binary home/not-home from her
phone's presence on the local network. The retained `home` flag is detection hysteresis,
not evidence of Gloria's whereabouts. It can never say which room — the house
map carries the geometry once a room is known from her own words.

Honesty rules:
  - Positive assertions only. A phone asleep, in airplane mode, or with a
    randomized MAC looks absent; so absence of the phone is silence, never
    the claim "she is out."
  - Hysteresis: home the moment the phone answers; considered away only after
    ABSENT_AFTER consecutive missed checks, because phones nap on wifi.
  - Fail-open: no config, no tools, no state -> every function returns its
    empty value and nothing anywhere changes.

Setup (one-time): write memory/home-presence-config.json:
    {"phone_ip": "192.168.x.x", "phone_mac": "aa:bb:cc:dd:ee:ff"}
Either field alone works; both is sturdier. iPhones randomize wifi MACs per
network ("Private Wi-Fi Address") — use the MAC the HOUSE network sees
(`ip neigh` while the phone is provably home), or pin the phone's DHCP lease
in the router and use the IP.

Cron (every 5 minutes):
    */5 * * * * python3 ~/.vintos/workspace/scripts/home_presence.py >> /tmp/home-presence.log 2>&1
"""
import json, math, os, subprocess, tempfile, time

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "home-presence-config.json")
STATE = os.path.join(MEMORY, "home-presence.json")
ABSENT_AFTER = 4          # consecutive misses before "not seen" (20 min at 5-min cron)
FRESH_S = 15 * 60         # a reading older than this asserts nothing


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def _ping(ip):
    try:
        return subprocess.run(["ping", "-c", "1", "-W", "2", ip],
                              capture_output=True, timeout=6).returncode == 0
    except Exception:
        return False


def _neigh_has(mac, ip):
    """The kernel neighbor table: sees devices that ignore ping. Only REACHABLE entries count -
    STALE/DELAY ones linger for minutes after a phone stops answering and would keep it 'seen'."""
    try:
        out = subprocess.run(["ip", "neigh", "show", "nud", "reachable"], capture_output=True,
                             timeout=6, text=True).stdout.lower()
    except Exception:
        return False
    for line in out.splitlines():
        if "failed" in line:
            continue
        if (mac and mac.lower() in line) or (ip and line.startswith(ip + " ")):
            return True
    return False


def probe(cfg=None):
    """One live look: True (seen), False (not seen), None (not configured)."""
    cfg = _load(CONFIG, {}) if cfg is None else cfg
    ip = str(cfg.get("phone_ip", "")).strip()
    mac = str(cfg.get("phone_mac", "")).strip()
    if not ip and not mac:
        return None
    if ip and _ping(ip):
        return True
    return _neigh_has(mac, ip)


def decide(prev, hit, now=None):
    """Pure hysteresis: a hit is home at once; misses accumulate before 'not seen'."""
    now = time.time() if now is None else now
    st = dict(prev) if isinstance(prev, dict) else {}
    if hit:
        if not st.get("home"):
            st["home_since"] = now
        st.update({"home": True, "misses": 0, "last_seen": now})
    else:
        st["misses"] = int(st.get("misses", 0)) + 1
        if st["misses"] >= ABSENT_AFTER:
            st["home"] = False
    st["checked"] = now
    return st


def context_line():
    """Age of an actual phone detection, not the latest check or her whereabouts."""
    st = _load(STATE, {})
    if not isinstance(st, dict) or st.get("home") is not True:
        return ""
    seen, checked, now = st.get("last_seen"), st.get("checked"), time.time()
    if any(type(t) not in (int, float) or (type(t) is float and not math.isfinite(t))
           for t in (seen, checked, now)):
        return ""
    if not 0 < seen <= checked <= now or now - seen > FRESH_S:
        return ""
    line = "Phone last detected on the house Wi-Fi %d seconds ago." % int(now - seen)
    if type(st.get("misses")) is int and st["misses"] > 0:
        line += " Latest check did not detect it."
    return line


def main():
    hit = probe()
    if hit is None:
        print("[presence] not configured (memory/home-presence-config.json)"); return
    prev = _load(STATE, {})
    st = decide(prev, hit)
    try:
        os.makedirs(MEMORY, exist_ok=True)
        _save_state(st)
    except Exception:
        pass
    try:                                             # review 94: home/away flips may move him, within limits
        import sensor_reactions as _sr
        if "home" in prev:
            _sr.observe("presence", bool(st.get("home")), at=st.get("checked"))
    except Exception:
        pass
    print("[presence] %s (misses=%s)" % ("seen - home" if hit else "not seen", st.get("misses", 0)))


def _save_state(state):
    """Readers see either the previous complete state or the new complete state."""
    fd, tmp = tempfile.mkstemp(prefix=".home-presence-", dir=os.path.dirname(STATE))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, STATE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


if __name__ == "__main__":
    main()
