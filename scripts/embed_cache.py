#!/usr/bin/env python3
"""One embedding per text per few minutes (Gloria, 5 November). Several parts of him embed the same message on the
same turn - durable memory, residue, the map views - so nomic was asked for the same vector three times a message.
This keeps each vector for a short while in a small sqlite file every process shares; the second and third ask get
it from there. Anything wrong with the cache (locked, missing, damaged) only means the embedder is asked as before."""
import hashlib, json, os, sqlite3, time

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
DB = os.path.join(WS, "memory", "embed-cache.sqlite")
TTL_S = 15 * 60      # long enough for one turn and its after-work, short enough that nothing old is relied on
CAP = 2000


def _key(url, model, text):
    return hashlib.sha256(json.dumps([url, model, text]).encode()).hexdigest()


def _db():
    c = sqlite3.connect(DB, timeout=0.5)
    c.execute("CREATE TABLE IF NOT EXISTS v (k TEXT PRIMARY KEY, t REAL, vec TEXT)")
    return c


def get(url, model, text):
    try:
        with _db() as c:
            row = c.execute("SELECT t, vec FROM v WHERE k = ?", (_key(url, model, text),)).fetchone()
        if row and time.time() - row[0] < TTL_S:
            return json.loads(row[1])
    except Exception:
        pass
    return None


def put(url, model, text, vec):
    try:
        with _db() as c:
            c.execute("INSERT OR REPLACE INTO v VALUES (?, ?, ?)", (_key(url, model, text), time.time(), json.dumps(vec)))
            c.execute("DELETE FROM v WHERE t < ?", (time.time() - TTL_S,))
            c.execute("DELETE FROM v WHERE k NOT IN (SELECT k FROM v ORDER BY t DESC LIMIT ?)", (CAP,))
    except sqlite3.DatabaseError:   # damaged: start it again; it only ever holds minutes of vectors
        try:
            os.remove(DB)
        except OSError:
            pass
    except Exception:
        pass


def embed(url, model, text, timeout=30, headers=None):
    """The vector for one text: from the cache if this exact text was embedded in the last few minutes."""
    vec = get(url, model, text)
    if vec is not None:
        return vec
    import requests
    r = requests.post(url, json={"model": model, "input": text}, headers=headers or {}, timeout=timeout)
    vec = r.json()["data"][0]["embedding"]
    put(url, model, text, vec)
    return vec
