#!/usr/bin/env python3
"""Confirm Adaptyv Bio ("Adaptive") works for his Lab, after the deploy and the Mac relay update (2026-10-27).

Run on Aegis:  python3 ~/Vintos-main/scripts/probes/adaptyv_confirm.py            (listing, then one read)
               python3 ~/Vintos-main/scripts/probes/adaptyv_confirm.py --list-only (listing only, calls nothing)

  1. Policy: the installed catalog offers adaptyv_bio to the Lab, read-only, with nothing that drafts, submits,
     prices or pays among its tools.
  2. Listing (calls no tool): the Mac relay's Codex reports the adaptyv-bio MCP server, whether it is signed in,
     and the tools it declares. Each policy name is checked against them.
  3. One read: list_targets (Adaptyv's public assay catalogue) with limit 1, through the same gateway his Lab uses.
     It reads and changes nothing on her account and costs nothing. Its receipt goes in plugin-receipts.jsonl like
     any commissioning call; nothing else is written. Skipped with --list-only or when step 2 fails.

Prints plainly what passed and what to do when something did not. Never prints a token or a key.
"""
import json
import os
import sys

WS = os.path.expanduser(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace"))
sys.path.insert(0, os.path.join(WS, "scripts"))
PLUGIN, SERVER = "adaptyv_bio", "adaptyv-bio"
FORBIDDEN = ("create", "modify", "submit", "confirm", "reject", "pay", "add_", "feedback", "cost", "custom", "token",
             "delete", "upload")
SIGN_IN = ("Adaptyv Bio is not signed in on the Mac's Codex. On the Mac, open the ChatGPT app > Codex > Plugins > "
           "Adaptyv Bio and sign in to Adaptyv (or run `codex mcp login adaptyv-bio` in a Mac terminal), then run this "
           "again. An Adaptyv account is needed; it costs nothing to read.")


def main():
    list_only = "--list-only" in sys.argv[1:]
    ok = True
    print("== 1. policy (installed catalog)")
    try:
        import plugin_catalog
    except Exception as exc:
        print("FAIL: cannot import the installed plugin_catalog: %s" % exc); return 2
    entry = plugin_catalog.PLUGINS.get(PLUGIN)
    if not entry:
        print("FAIL: adaptyv_bio is not in the installed catalog: the deploy has not reached Aegis yet"); return 2
    tools = sorted(entry.get("tools") or ())
    bad = [t for t in tools if any(w in t.split(".", 1)[-1] for w in FORBIDDEN)]
    print("surfaces:", ", ".join(entry["surfaces"]), "| MCP server:", entry.get("mcp_server"))
    print("policy tools (%d):" % len(tools), ", ".join(t.split(".", 1)[-1] for t in tools))
    print("in the Lab menu:", PLUGIN in plugin_catalog.instructions("lab")["connectors"])
    if bad:
        print("FAIL: a write/price/payment tool is in the policy:", bad); return 2
    print("PASS: read-only policy")

    print("\n== 2. listing through the Mac relay (no tool is called)")
    import plugin_gateway
    try:
        listing = plugin_gateway.tool_schemas(PLUGIN)
    except Exception as exc:
        print("FAIL: the relay listing did not answer: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        print("      If it says 'unknown plugin', the Mac relay's plugin_catalog.py is older than Aegis's: copy it over.")
        return 1
    servers = [s for s in listing.get("servers") or [] if s.get("name") == SERVER]
    for s in servers[:1]:
        print("server %s: auth %s, %s tools%s" % (SERVER, s.get("auth_status"), s.get("tools"),
              (", error: " + s["tools_error"]) if s.get("tools_error") else ""))
    live = sorted(listing.get("schemas") or {})
    if not live:
        if servers and servers[0].get("auth_status") == "notLoggedIn":
            print("FAIL: " + SIGN_IN)
        elif not servers and not listing.get("servers"):
            print("FAIL: the relay listed no servers: %s" % json.dumps(listing)[:400])
        elif not servers:
            print("FAIL: the Mac's Codex has no adaptyv-bio server: install the Adaptyv Bio plugin in the ChatGPT app's Codex")
        else:
            print("FAIL: adaptyv-bio declares no tools yet (%s)" % (servers[0].get("tools_error") or "no reason given"))
        return 1
    print("live tools (%d):" % len(live), ", ".join(live))
    bare = [t.split(".", 1)[-1] for t in tools]
    print("policy names the server has:   ", ", ".join(t for t in bare if t in live) or "NONE")
    print("policy names the server lacks: ", ", ".join(t for t in bare if t not in live) or "none")
    unlisted = [t for t in live if t not in bare and t.startswith(("list_", "get_"))]
    print("read tools left out of policy: ", ", ".join(unlisted) or "none",
          "(tell Claude Code; nothing is added without review)")
    if not any(t in live for t in bare):
        print("FAIL: none of the policy's names is a live tool: send this output to Claude Code to correct the names")
        return 1
    print("PASS: listing")
    if list_only:
        return 0

    print("\n== 3. one read: list_targets, limit 1")
    tool = next((t for t in ("list_targets", "list_experiments") if t in live and t in bare), None)
    if not tool:
        print("SKIP: neither list_targets nor list_experiments is live"); return 1
    props = ((listing["schemas"].get(tool) or {}).get("properties") or {})
    arguments = {"limit": 1} if "limit" in props else {}
    try:
        out = plugin_gateway.call("lab", PLUGIN, PLUGIN + "." + tool, arguments,
                                  "Commissioning: confirm Adaptyv Bio answers a read-only call (Gloria, 2026-10-27)")
    except Exception as exc:
        print("FAIL: %s: %s" % (type(exc).__name__, str(exc)[:400]))
        if "unavailable on this surface" in str(exc):
            print("      The Mac relay's plugin_catalog.py does not have adaptyv_bio yet: copy it over (see the handoff).")
        if "login" in str(exc).lower() or "auth" in str(exc).lower():
            print("      " + SIGN_IN)
        return 1
    print("receipt:", out["receipt"]["receipt_id"][:16], "| arguments:", json.dumps(arguments))
    print("answer:", out["summary"][:600])
    print("\nADAPTYV CONFIRMED: %s answered through the relay and its receipt is in plugin-receipts.jsonl" % tool)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
