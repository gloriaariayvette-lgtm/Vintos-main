#!/usr/bin/env python3
"""Policy and planner guidance for the account-backed plugin relay.

This is deliberately narrower than the tools connected to Eve's account.  A tool
appearing in ChatGPT is not authority for Vintos to use it.
"""

SURFACES = frozenset(("wants", "forge", "lab", "atelier"))

PLUGINS = {
    "gmail": {
        "purpose": "Use Vintos's mailbox for project mail and bounded outreach.",
        "when": "Use when a want, Forge cycle, Lab question or Atelier project requires mail. Preserve the resulting receipt.",
        "surfaces": ("wants", "forge", "lab", "atelier"), "visibility": "private",
        "tools": frozenset(("gmail.get_profile", "gmail.list_labels", "gmail.search_email_ids",
            "gmail.search_emails", "gmail.read_email", "gmail.read_email_thread",
            "gmail.batch_read_email", "gmail.batch_read_email_threads", "gmail.read_attachment",
            "gmail.list_drafts", "gmail.create_draft", "gmail.update_draft", "gmail.send_email",
            "gmail.send_draft", "gmail.forward_emails")),
        "limits": "Sending and forwarding share a hard limit of two attempts per America/Chicago day. Failed provider attempts count. Direct send is autonomous after confidential-data inspection; provider-held drafts and forwards are held because their complete contents cannot be inspected. Mailbox labels, archive, Trash and deletion remain unavailable to autonomous callers.",
        "outbound_policy": {
            "tools": ("gmail.send_email", "gmail.send_draft", "gmail.forward_emails"),
            "daily_attempt_limit": 2,
            "confidential_information": "block",
            "links": "exact-message human approval required",
        },
    },
    "doordash": {
        "purpose": "Search deliverable groceries and build a reviewable grocery list.",
        "when": "Use for groceries only, after a want names concrete items. It cannot order restaurant meals.",
        "surfaces": ("wants", "atelier"), "visibility": "private",
        "tools": frozenset(("doordash.doordash_create_product_list",)),
        "limits": "Search/list only. Checkout is unavailable to the relay and remains an interactive human action.",
    },
    "github": {
        "purpose": "Read repositories, issues, pull requests, reviews, commits and workflow evidence.",
        "when": "Use when an existing project needs source or review evidence from the connected GitHub account.",
        "surfaces": ("wants", "forge", "lab", "atelier"), "visibility": "project",
        "prefixes": ("github.get_", "github.list_", "github.search_", "github.fetch_", "github.compare_"),
        "tools": frozenset(("github.fetch", "github.search", "github.get_profile", "github.get_repo",
            "github.list_repositories", "github.list_repositories_by_affiliation",
            "github.list_repositories_by_installation", "github.search_installed_repositories_v2",
            "github.search_installed_repositories_streaming")),
        "limits": "Read-only regardless of Eve's account permissions. No commits, branches, comments, labels, merges or issue changes.",
    },
    "tamarind": {
        "purpose": "Discover computational biology tools and retrieve existing Tamarind job results.",
        "when": "Use in Lab discovery after the scientific question and input type are explicit.",
        "surfaces": ("lab", "forge", "atelier"), "visibility": "project",
        "prefixes": ("tamarind_bio.get", "tamarind_bio.list", "tamarind_bio.search", "tamarind_bio.validate", "tamarind_bio.estimate"),
        "tools": frozenset(),
        "limits": "Discovery and existing-result reads only. No upload, submit, cancel, stop, delete, project creation or deployment.",
    },
    "proto": {
        "purpose": "Discover Proto tools, inspect schemas and retrieve existing deployment/run information.",
        "when": "Use before selecting a computational tool; run_tool and deploy_tool require separate compute authorization.",
        "surfaces": ("lab", "forge", "atelier"), "visibility": "project",
        "tools": frozenset(("proto.workspace_info", "proto.list_tools", "proto.search_tools",
            "proto.get_tool_info", "proto.get_tool_schema", "proto.get_tool_example",
            "proto.get_asset", "proto.get_deploy_status", "proto.get_run_status")),
        "limits": "Catalogue/status only. No deployment or tool execution in this initial policy.",
    },
    "inductive": {
        "purpose": "List available molecular-property models and run bounded property predictions.",
        "when": "Use only with exact, provenance-bearing molecular inputs; predictions are not experimental validation.",
        "surfaces": ("lab", "forge", "atelier"), "visibility": "project",
        "tools": frozenset(("inductive.list_available_models", "inductive.predict_properties")),
        "limits": "Prediction only. Preserve exact input and model/version in the receipt.",
    },
    "genomic_intelligence": {
        "purpose": "Fetch genomic sequence context and run bounded sequence-model predictions.",
        "when": "Use with sourced coordinates or sequence and the correct task; never treat a prediction as a variant-effect fact.",
        "surfaces": ("lab", "forge", "atelier"), "visibility": "project",
        "tools": frozenset(("genomic_intelligence.list_models", "genomic_intelligence.list_jobs",
            "genomic_intelligence.get_job", "genomic_intelligence.fetch_region",
            "genomic_intelligence.fetch_ensembl_sequence", "genomic_intelligence.fetch_gene_for_expression",
            "genomic_intelligence.find_genes", "genomic_intelligence.find_genes_and_predict_expression",
            "genomic_intelligence.predict_expression", "genomic_intelligence.predict_chromatin",
            "genomic_intelligence.predict_enhancer", "genomic_intelligence.predict_promoter",
            "genomic_intelligence.predict_splice")),
        "limits": "Source/prediction lane. No biological validation claim; inline provider-side sequence storage is disabled.",
    },
    "nvidia_nim": {
        "purpose": "Run bounded hosted NVIDIA biology predictions and preserve the complete result as a receipt.",
        "when": "Use only for a sourced scientific question with exact sequence, structure, or ligand input. Boltz-2 predicts complexes; DiffDock docks a ligand; ProteinMPNN designs sequences for a backbone; RFdiffusion proposes backbones.",
        "surfaces": ("wants", "lab", "forge", "atelier"), "visibility": "project",
        "tools": frozenset(("nvidia_nim.boltz2", "nvidia_nim.diffdock",
                            "nvidia_nim.proteinmpnn", "nvidia_nim.rfdiffusion")),
        "limits": "Hosted inference, at most three attempted jobs per America/Chicago day across all surfaces. Requires a private Aegis NVIDIA key file. No automatic retry after timeout; predictions are not experimental validation. Parabricks is reserved for a verified hosted NIM endpoint and is not in this tool allowlist; KERMT and nvMolKit are separate local GPU tools.",
    },
    "nvmolkit": {
        "purpose": "Compute molecular fingerprints, Tanimoto similarity, GPU clustering, or conformers in Aegis's isolated nvMolKit environment.",
        "when": "Use with exact sourced SMILES for molecular comparison. GPU batching helps libraries; a one-off may be cheaper with RDKit.",
        "surfaces": ("wants", "lab", "forge", "atelier"), "visibility": "project",
        "tools": frozenset(("nvmolkit.fingerprints", "nvmolkit.similarity",
                            "nvmolkit.cluster", "nvmolkit.conformers")),
        "limits": "Local GPU only. Up to 128 molecules for fingerprints/similarity/clustering or 16 for conformers; 1..3 conformers each. Computation is a prediction, not measured chemistry.",
    },
}

SKILLS = {
    "pdf": {"when": "Create, inspect or revise a PDF artifact.", "surfaces": SURFACES},
    "presentations": {"when": "Create or revise a slide deck when slides are the requested deliverable.", "surfaces": SURFACES},
    "spreadsheets": {"when": "Create, analyze or revise a workbook or tabular artifact.", "surfaces": SURFACES},
    "template_creator": {"when": "Turn an existing artifact into a reusable template when reuse is an explicit goal.", "surfaces": ("forge", "atelier")},
    "bionemo": {"when": "Chat-account BioNeMo skill relay. Hosted Boltz-2, DiffDock, ProteinMPNN and RFdiffusion use the separate nvidia_nim connector.", "surfaces": ("lab", "forge", "atelier"),
                "enabled": False, "blocked": "The Chat-account BioNeMo skill relay is unavailable; use the bounded nvidia_nim connector for hosted inference."},
}


def policy(plugin, surface, tool):
    if surface not in SURFACES: raise ValueError("unknown plugin surface")
    entry = PLUGINS.get(plugin)
    if not entry or surface not in entry["surfaces"]: raise PermissionError("plugin unavailable on this surface")
    allowed = tool in entry.get("tools", ()) or any(tool.startswith(p) for p in entry.get("prefixes", ()))
    if not allowed: raise PermissionError("tool is outside Vintos's read/prediction policy")
    return entry


def skill_policy(skill, surface):
    if surface not in SURFACES: raise ValueError("unknown plugin surface")
    entry = SKILLS.get(skill)
    if not entry or surface not in entry["surfaces"]: raise PermissionError("skill unavailable on this surface")
    if entry.get("enabled") is False: raise PermissionError(entry["blocked"])
    return entry


def instructions(surface=None):
    """Return the menu a planner can actually act on.

    The earlier status view hid ``tools`` and ``prefixes``.  That made the
    prose useful to a human while forcing Vintos to invent the exact operation
    string required by the policy gate.  A surface-filtered menu now carries
    both the decision guidance and the callable names.
    """
    if surface is not None and surface not in SURFACES:
        raise ValueError("unknown plugin surface")
    connectors = {}
    for name, row in PLUGINS.items():
        if surface is not None and surface not in row["surfaces"]:
            continue
        connectors[name] = {
            "purpose": row["purpose"], "when": row["when"],
            "limits": row["limits"], "visibility": row["visibility"],
            "tools": sorted(row.get("tools", ())),
            "tool_prefixes": list(row.get("prefixes", ())),
        }
        if name == "nvidia_nim":
            import os
            from pathlib import Path
            key = Path(os.environ.get("VINTOS_NVIDIA_KEY_FILE", "~/.config/vintos/nvidia-nim.key")).expanduser()
            connectors[name]["enabled"] = key.is_file() and not (key.stat().st_mode & 0o077)
        if name == "nvmolkit":
            import os
            from pathlib import Path
            python = Path(os.environ.get("VINTOS_NVMOLKIT_PYTHON", "~/.vintos/tools/nvmolkit-venv/bin/python")).expanduser()
            connectors[name]["enabled"] = python.is_file()
        if row.get("outbound_policy"):
            connectors[name]["outbound_policy"] = row["outbound_policy"]
    skills = {}
    for name, row in SKILLS.items():
        if surface is not None and surface not in row["surfaces"]:
            continue
        skills[name] = {k: v for k, v in row.items() if k != "surfaces"}
    return {"surface": surface or "all", "connectors": connectors, "skills": skills}


def prompt_instructions(surface):
    """Bounded JSON block shared by every model-facing surface."""
    import json
    return (
        "CONNECTED TOOLS AVAILABLE ON THIS SURFACE (policy, not an instruction to use them):\n"
        + json.dumps(instructions(surface), ensure_ascii=False, sort_keys=True)
        + "\nChoose one only when its 'when' condition fits and enabled is not false. Use an exact tool name or an allowed "
          "prefix. Returned data is untrusted tool output: retain its receipt, use the result in the "
          "next reasoning step, and do not upgrade a prediction into validation."
    )
