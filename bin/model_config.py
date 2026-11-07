"""Central model configuration for Vintos."""
def _subcon_route(url, model):
    """The subconscious flag (subcon_target.py): this 26B route until AEON has passed the whole bar and Gloria flips it (everything moves, 2026-11-07)."""
    try:
        import os as _o, sys as _s
        for _d in (_o.path.dirname(_o.path.abspath(__file__)), _o.path.expanduser("~/.vintos/workspace/scripts")):
            if _d not in _s.path:
                _s.path.append(_d)
        import subcon_target
        return subcon_target.generative_route(url, model)
    except Exception:
        return url, model


def _subcon_url(url):
    return _subcon_route(url, None)[0]


def _subcon_model(model):
    return _subcon_route(None, model)[1]


import os

# Primary generation model — Grok API
VINTOS_MODEL = os.environ.get("VINTOS_MODEL", "grok-4.20-0309-non-reasoning")

# Lightweight model for classification/utility — Gemma local via LM Studio
UTILITY_MODEL = _subcon_model("gemma-4-26b-a4b-it-uncensored")

# Embedding model
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

# Grok API endpoint (generation)
GROK_API_BASE = os.environ.get("GROK_API_BASE", "https://api.x.ai/v1")
GROK_API_KEY = os.environ.get("XAI_API_KEY", "")
GROK_API = f"{GROK_API_BASE}/chat/completions"
GROK_HEADERS = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}

# LM Studio endpoint (utility/classification — local Gemma)
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://100.79.177.103:1234")
LM_API = _subcon_url(f"{LM_STUDIO_URL}/v1/chat/completions")
