#!/usr/bin/env python3
"""Fail-closed outbound-mail inspection shared by both relay endpoints."""
import hashlib
import json
import os
from pathlib import Path
import re

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
LABELED_SECRET_RE = re.compile(
    r"(?i)\b(api[ _-]?key|access[ _-]?token|refresh[ _-]?token|password|credential|"
    r"client[ _-]?secret|authorization)\b\s*[:=]\s*[^\s,;]{4,}"
)
TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|"
                      r"Bearer\s+[A-Za-z0-9._~+/=-]{12,})\b", re.I)
MESSAGE_KEYS = frozenset(("to", "cc", "bcc", "recipient", "recipients", "subject", "body",
                          "content", "message", "text", "html", "html_body", "text_body"))


class PolicyHold(PermissionError):
    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__(receipt["type"])


def request_digest(arguments):
    return hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _message_strings(value, parent=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _message_strings(child, str(key).lower())
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _message_strings(child, parent)
    elif isinstance(value, str) and parent in MESSAGE_KEYS:
        yield value


def _secret_values(root):
    base = Path(root).expanduser()
    if not base.is_dir():
        return set()
    found = set()
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        try:
            raw = path.read_text(errors="strict").strip()
        except (OSError, UnicodeError):
            continue
        candidates = [raw] + [line.strip() for line in raw.splitlines()]
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        stack = [parsed]
        while stack:
            item = stack.pop()
            if isinstance(item, dict): stack.extend(item.values())
            elif isinstance(item, list): stack.extend(item)
            elif isinstance(item, (str, int, float)): candidates.append(str(item).strip())
        found.update(x for x in candidates if len(x) >= 8)
    return found


def outbound_findings(arguments, secrets_root=None):
    """Return rule names and URLs without ever returning matched secret material."""
    strings = list(_message_strings(arguments))
    joined = "\n".join(strings)
    rules = []
    if LABELED_SECRET_RE.search(joined): rules.append("labeled_credential")
    if TOKEN_RE.search(joined): rules.append("token_format")
    root = secrets_root or os.environ.get("VINTOS_SECRETS", "~/.vintos/secrets")
    if any(value in joined for value in _secret_values(root)): rules.append("installed_secret_value")
    links = sorted(set(URL_RE.findall(joined)))
    return {"rules": sorted(set(rules)), "links": links, "request_sha256": request_digest(arguments)}


def result_links(result):
    """Find links in connected mail output; this function never opens them."""
    try:
        text = json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        return []
    return sorted(set(URL_RE.findall(text)))

