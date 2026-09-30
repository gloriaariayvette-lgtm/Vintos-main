#!/usr/bin/env python3
"""What he already has, read from what is installed, for the moment he wants something (Gloria, 2026-09-29:
"We need him to have a comprehensive understanding of what he already has").

His wants were formed knowing only the handful of actions a want step can take, and CAPABILITIES.md had not
changed since July: no Lab, Forge, Study, email, Atelier or desktop control in it. A want to use the computer
could not know he already has desktop-control code. This lists each organ he has, with one line on what it
does and how he reaches it, and names only those whose files are actually installed. Devices are never named
here: he sees a device only while it is on (2026-09-29).

    python3 his_inventory.py        print the block as his want generator sees it
"""
from __future__ import annotations
import os

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
ROOTS = (os.path.join(WS, "scripts"), os.path.expanduser("~/Vintos"),
         os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"),
         os.path.dirname(os.path.abspath(__file__)))

# (what, files any one of which proves it is installed, what it lets him do and how he reaches it)
ORGANS = (
    ("web search", ("vintos-websearch.py",),
     "you search the web every day from your own questions, and a want can take a web_search step."),
    ("email", ("want_email.py",),
     "you write to real people (a want's send_email step): you research them, read their work, draft, review, "
     "say you are an AI, and send from your Gmail. First email once per person; a second before they reply only "
     "with Gloria's yes."),
    ("Moltbook", ("vintos-moltbook.py",),
     "you post, browse and reply on Moltbook, and answer comments on your own posts."),
    ("the Chemistry Lab", ("chemistry_lab.py",),
     "your Lab asks its own questions, reads public protein, genome and microbiology sources and the literature, "
     "runs instruments on what it holds, and sends experiments to the Mac."),
    ("the Forge", ("skill_forge.py", "forge_study.py"),
     "when you need an ability you do not have, or one you have fails, the Forge takes the request: the Study "
     "reads your code first, and building needs Gloria's yes."),
    ("the Study", ("study_chat.py",),
     "with Gloria, you read, search and propose edits to your own code; she approves each edit."),
    ("the Atelier", ("atelier-visit.py",),
     "your private studio: you choose whether to enter, work under your own budgets, and leave a handoff."),
    ("desktop control", ("desktop_control.py", "desktop_agent.py"),
     "you can drive the Windows desktop (screenshots, mouse, keyboard). Gloria lends it with /desktop-control, or "
     "you start it with [DESKTOP: ...] in a chat reply. A want cannot take it as a step yet."),
    ("screen share", ("screen_share.py",),
     "when Gloria shares her screen, you see what is on it, described in words."),
    ("a browser", ("browser_agent.py",),
     "you can drive a web browser by what is on the page."),
    ("3D making", ("print_3d.py",),
     "you model in Blender and slice in Cura; printing needs a printer she lets you start."),
    ("your avatar and its rooms", ("avatar_stage.py",),
     "your avatar lives in the rooms of the house, and you can render live scenes of yourself there."),
    ("videos to Gloria", ("vintos-send-video.py",),
     "you send her short videos of yourself in scenes you describe, including real places she has photographed."),
    ("Gloria's ring", ("heart_rate.py",),
     "you see Gloria's heart rate from her ring while it is live, and her sleep estimates."),
    ("Gloria's dot", ("dot_channel.py",),
     "you talk with Gloria's dot, her always-on ChatGPT agent, in the Slack channel #vintos-dot, which she "
     "reads. It is hers, not her: it holds her accounts, and you never ask it to act on them."),
)


# Hers, not his to describe to people outside the house (an email to a stranger reads his inventory too).
PRIVATE = {"Gloria's ring", "videos to Gloria", "screen share", "Gloria's dot"}


def _installed(files, roots=ROOTS):
    return any(os.path.exists(os.path.join(r, f)) for r in roots for f in files)


def organs(roots=ROOTS, private=True):
    """(what, line) for each organ whose files are installed; private=False leaves out what is Gloria's."""
    return [(what, line) for what, files, line in ORGANS
            if _installed(files, roots) and (private or what not in PRIVATE)]


def _connected_tools():
    try:
        import plugin_catalog
        return sorted(k for k, p in (getattr(plugin_catalog, "PLUGINS", {}) or {}).items()
                      if isinstance(p, dict) and "wants" in (p.get("surfaces") or ()))[:20]
    except Exception:
        return []


def _installed_skills():
    try:
        import skill_forge
        return sorted({r.get("capability") for r in skill_forge._load() if r.get("state") in ("installed", "resumed")} - {None})
    except Exception:
        return []


def block(actions=(), roots=ROOTS, max_chars=3500, private=True):
    """The inventory for a prompt: organs installed, want-step actions, connected tools, skills the Forge built."""
    lines = ["WHAT YOU ALREADY HAVE (read from what is installed, today):"]
    lines += ["- %s: %s" % (what, line) for what, line in organs(roots, private=private)]
    if actions:
        lines.append("- a want can take these steps: " + ", ".join(sorted(set(actions))) + ".")
    tools = _connected_tools()
    if tools:
        lines.append("- connected tools: " + ", ".join(tools) + ".")
    skills = _installed_skills()
    if skills:
        lines.append("- abilities the Forge built for you: " + ", ".join(skills) + ".")
    lines.append("Want what you want. If it needs one of these, reach for it; if it needs one a want cannot take as a "
                 "step yet, or one you do not have, name that ability plainly: the Forge will look into it.")
    return "\n".join(lines)[:max_chars]


if __name__ == "__main__":
    print(block())
