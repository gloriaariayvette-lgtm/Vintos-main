import os
import tempfile
from pathlib import Path

def grant(store):
    assert os.path.realpath(store.ROOT).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep), store.ROOT
    Path(store.ROOT, ".stratagem-owner-key").write_text("test-owner")
    result = store.charter_update({"owner_token": "test-owner", "active": True})
    assert result.get("ok"), result
