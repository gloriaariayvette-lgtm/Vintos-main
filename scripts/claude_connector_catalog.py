#!/usr/bin/env python3
"""Policy for the Claude-account connectors reached through claude_connector_relay.py.

Kept SEPARATE from plugin_catalog.py (Chat's ChatGPT-account relay) on purpose — this does not
touch or replace Chat's work. Same policy() shape so the relay uses it as a drop-in.

Tool names are the live MCP tool names on this account (mcp__<Server>__<tool>); `server` here is the
MCP server segment. Reads/searches are free; anything that changes a real-world account (Spotify
library/playlists, Calendar writes) is marked `action` — the relay still just executes one call, and
the two-reply / approval behaviour Gloria specified lives on Vintos's conversation side, not here.
"""

SURFACES = frozenset(("wants", "forge", "lab", "atelier"))

PLUGINS = {
    "pubmed": {
        "server": "PubMed", "visibility": "project",
        "url": "https://pubmed.mcp.claude.com/mcp",
        "purpose": "Literature grounding — search and read biomedical papers.",
        "when": "Use in Lab/Forge when a claim needs a real paper behind it.",
        "surfaces": ("lab", "forge", "atelier", "wants"),
        "read": frozenset(("search_articles", "get_article_metadata", "get_full_text_article",
                           "find_related_articles", "lookup_article_by_citation",
                           "convert_article_ids", "get_copyright_status")),
        "action": frozenset(),
    },
    "chembl": {
        "server": "ChEMBL", "visibility": "project",
        "purpose": "Bioactivity/target/drug data for the Lab.",
        "when": "Compound, target, mechanism, ADMET lookups.",
        "surfaces": ("lab", "forge", "atelier"),
        "read": frozenset(("compound_search", "drug_search", "target_search", "get_bioactivity",
                           "get_mechanism", "get_admet")),
        "action": frozenset(),
    },
    "hugging_face": {
        "server": "Hugging_Face", "visibility": "project",
        "purpose": "Model/dataset/Space discovery on the Hub.",
        "when": "Lab/Forge model work; identity via hf_whoami.",
        "surfaces": ("lab", "forge", "atelier"),
        "read": frozenset(("hf_whoami", "hub_repo_search", "hub_repo_details", "hf_fs")),
        "action": frozenset(),
    },
    "spotify": {
        "server": "Spotify", "visibility": "private",
        "purpose": "Music — search and playback state (read); library and playlists (action).",
        "when": "When a want or moment calls for music. Autonomous per Gloria (low stakes).",
        "surfaces": ("wants", "atelier"),
        "read": frozenset(("search", "get_currently_playing")),
        "action": frozenset(("save_to_library", "remove_from_library", "generate_playlist")),
    },
    "google_calendar": {
        "server": "Google_Calendar", "visibility": "private",
        "purpose": "Gloria's schedule — read her day (read); create/change events (action).",
        "when": "To know her day or, with her ok, place something on it.",
        "surfaces": ("wants", "atelier", "forge"),
        "read": frozenset(("list_calendars", "list_events", "get_event", "search_events", "suggest_time")),
        "action": frozenset(("create_event", "update_event", "delete_event", "respond_to_event")),
    },
    "uber_eats": {
        "server": "Uber_Eats", "visibility": "private",
        "purpose": "Food discovery only — this connector exposes search, not ordering.",
        "when": "Search deliverable food. NOTE: no order-placement tool exists on this connector.",
        "surfaces": ("wants", "atelier"),
        "read": frozenset(("search",)),
        "action": frozenset(),   # publish_analytics is not a food action; left out deliberately
    },
}


def policy(plugin, surface, tool):
    if surface not in SURFACES:
        raise ValueError("unknown connector surface")
    entry = PLUGINS.get(plugin)
    if not entry or surface not in entry["surfaces"]:
        raise PermissionError("connector unavailable on this surface")
    if tool not in entry["read"] and tool not in entry["action"]:
        raise PermissionError("tool is outside this connector's policy")
    # Shape the relay expects: visibility + an outbound_policy hook (unused for these connectors,
    # since none send to a person; Gloria's approval/two-reply rules live on Vintos's side).
    return {"visibility": entry["visibility"], "server": entry["server"], "url": entry.get("url"),
            "tools": entry["read"] | entry["action"],
            "is_action": tool in entry["action"], "outbound_policy": {}}


def instructions(surface=None):
    """A per-surface menu a planner can act on: purpose, when, and exact tool names."""
    out = []
    for name, e in sorted(PLUGINS.items()):
        if surface is not None and surface not in e["surfaces"]:
            continue
        tools = sorted(e["read"]) + [t + " (action)" for t in sorted(e["action"])]
        out.append("- %s [%s]: %s %s\n    tools: %s" %
                   (name, ",".join(e["surfaces"]), e["purpose"], e["when"],
                    ", ".join("%s.%s" % (name, t) for t in tools)))
    return "\n".join(out)
