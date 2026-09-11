"""Gallery routes, moved verbatim from server.py (Q2 Phase 3, cut 1)."""
import os, json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
router = APIRouter()

# === Dream Art Gallery ===

@router.get("/api/art/gallery")
async def get_gallery(limit: int = 50):
    """Vintos's dream paintings — generated while he sleeps."""
    gallery_file = os.path.join(MEMORY, "art", "gallery.json")
    if not os.path.exists(gallery_file):
        return {"paintings": []}
    try:
        with open(gallery_file) as f:
            paintings = json.load(f)
        paintings = [p for p in paintings if not p.get("taken_down")]
        paintings.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return {"paintings": paintings[:limit]}
    except:
        return {"paintings": []}


@router.get("/api/art/painting/{filename}")
async def get_painting(filename: str):
    """Serve a dream painting image."""
    from fastapi.responses import FileResponse
    # Sanitize filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    painting_path = os.path.join(MEMORY, "art", filename)
    if os.path.exists(painting_path):
        if filename.endswith(".png"):
            return FileResponse(painting_path, media_type="image/png")
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            return FileResponse(painting_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Painting not found")


