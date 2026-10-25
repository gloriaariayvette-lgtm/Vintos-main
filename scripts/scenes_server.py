#!/usr/bin/env python3
"""Static media for the projector, with HTTP Range support.

python -m http.server answers 200 to a Range request. Cast receivers ask for a
byte range before they will play video and stall at BUFFERING when they do not
get 206 - which is why images always appeared and video never did.

Cast receivers on the house network fetch a file by its exact path, so that is all
this serves: one media file at a time. No directory is ever listed and nothing
hidden or non-media is served (2026-10-25: the old copy listed his whole art store
to anyone on the network).
"""
import os, re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.environ.get("VINTOS_SCENES_ROOT", os.path.expanduser("~/.vintos/workspace/memory/art"))
PORT = int(os.environ.get("VINTOS_SCENES_PORT", "8501"))
MEDIA = {".mp4", ".webm", ".mov", ".m4v", ".mp3", ".m4a", ".wav", ".ogg", ".flac",
         ".png", ".jpg", ".jpeg", ".gif", ".webp"}

class _Limited:
    """copyfile reads to EOF; a range response must stop at its last byte."""
    def __init__(self, f, n): self.f, self.n = f, n
    def read(self, size=-1):
        if self.n <= 0: return b""
        if size is None or size < 0: size = self.n
        d = self.f.read(min(size, self.n)); self.n -= len(d); return d
    def close(self): self.f.close()

def servable(path, root=None):
    """A regular media file inside the root, not hidden; never a directory."""
    root = os.path.realpath(root or ROOT)
    real = os.path.realpath(path)
    if not real.startswith(root + os.sep) or not os.path.isfile(real): return False
    rel = os.path.relpath(real, root)
    if any(part.startswith(".") for part in rel.split(os.sep)): return False
    return os.path.splitext(real)[1].lower() in MEDIA

class H(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)
    def log_message(self, *a): pass
    def list_directory(self, path):
        self.send_error(404); return None
    def send_head(self):
        path = self.translate_path(self.path)
        if not servable(path):
            self.send_error(404); return None
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404); return None
        size = os.fstat(f.fileno()).st_size
        m = re.match(r"bytes=(\d*)-(\d*)\s*$", rng.strip())
        if not m:
            f.close(); self.send_error(400); return None
        a, b = m.group(1), m.group(2)
        if a == "":
            start, end = max(0, size - int(b or 0)), size - 1
        else:
            start, end = int(a), (int(b) if b else size - 1)
        end = min(end, size - 1)
        if start > end or start >= size:
            f.close(); self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0"); self.end_headers(); return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        f.seek(start)
        return _Limited(f, end - start + 1)

if __name__ == "__main__":
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer(("", PORT), H).serve_forever()
