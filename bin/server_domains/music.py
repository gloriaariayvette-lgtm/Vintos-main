"""Music gallery routes, moved verbatim from server.py (Q2 Phase 3, cut 2)."""
import os, json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
router = APIRouter()

# === Music Gallery ===

@router.get("/api/art/music")
async def get_music(limit: int = 20):
    """Vintos's composed music — generated from emotional states and dreams."""
    music_file = os.path.join(MEMORY, "art", "music", "music.json")
    if not os.path.exists(music_file):
        return {"compositions": []}
    try:
        with open(music_file) as f:
            data = json.load(f)
        compositions = []
        for gen in data.get("generated", []):
            tracks = []
            for t in gen.get("tracks", []):
                local = t.get("local_file", "")
                fname = os.path.basename(local) if local else ""
                # Check for cover art
                cover = fname.replace(".mp3", ".jpeg") if fname else ""
                cover_path = os.path.join(MEMORY, "art", "music", cover)
                tracks.append({
                    "version": t.get("version"),
                    "duration": t.get("duration"),
                    "file": fname,
                    "cover": cover if os.path.exists(cover_path) else None,
                })
            compositions.append({
                "title": gen.get("title"),
                "style": gen.get("style"),
                "description": gen.get("description"),
                "model": gen.get("model"),
                "generated_at": gen.get("generated_at"),
                "tracks": tracks,
            })
        compositions.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
        return {"compositions": compositions[:limit]}
    except Exception as e:
        return {"compositions": [], "error": str(e)}


@router.get("/api/art/music/stream/{filename}")
async def stream_music(filename: str):
    """Stream a music file."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    music_path = os.path.join(MEMORY, "art", "music", filename)
    if os.path.exists(music_path):
        if filename.endswith(".mp3"):
            return FileResponse(music_path, media_type="audio/mpeg")
        elif filename.endswith(".wav"):
            return FileResponse(music_path, media_type="audio/wav")
        elif filename.endswith(".jpeg") or filename.endswith(".jpg"):
            return FileResponse(music_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Music file not found")


