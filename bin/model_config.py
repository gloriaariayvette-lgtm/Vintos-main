"""Central model configuration for Vintos."""
import os

# Primary generation model — Grok API
VINTOS_MODEL = os.environ.get("VINTOS_MODEL", "grok-4.20-0309-non-reasoning")

# Lightweight model for classification/utility — Gemma local via LM Studio
UTILITY_MODEL = "google/gemma-4-12b-qat"

# Embedding model
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

# Grok API endpoint (generation)
GROK_API_BASE = os.environ.get("GROK_API_BASE", "https://api.x.ai/v1")
GROK_API_KEY = os.environ.get("XAI_API_KEY", "")
GROK_API = f"{GROK_API_BASE}/chat/completions"
GROK_HEADERS = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}

# LM Studio endpoint (utility/classification — local Gemma)
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://172.18.16.1:1234")
LM_API = f"{LM_STUDIO_URL}/v1/chat/completions"
