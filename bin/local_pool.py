#!/usr/bin/env python3
"""local_pool.py — which machine a local model call goes to (Gloria 2026-11-05).

Each task has a ranked list of models. The first model some machine is serving with room above that machine's
reserve wins, on its home machine, or the next machine serving it when home has no room. A background thread re-reads every machine every REFRESH_S
seconds (room report over the existing SSH access), so a call never waits on SSH.

Config is read from ~/.vintos/pool/{machines,backends,tasks}.json, not kept in this public repo. With no config,
an unknown task, or a reading older than STALE_S, choose() returns nothing and the caller's old direct route is
used. Nothing here loads or starts a model.
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CONFIG_DIR = os.path.expanduser("~/.vintos/pool")
ROOM_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pool_room.py")
REFRESH_S = 15
STALE_S = 60
GiB = 1024 ** 3


def load_config(d=None):
    """(machines by name, backends, tasks), or None if any file is missing or unreadable."""
    d = d or CONFIG_DIR
    try:
        machines = {m["name"]: m for m in json.load(open(os.path.join(d, "machines.json")))}
        backends = json.load(open(os.path.join(d, "backends.json")))
        tasks = json.load(open(os.path.join(d, "tasks.json")))
        return machines, backends, tasks
    except Exception:
        return None


def read_room(m):
    """Room report for machine m, or None (off or unreachable counts as unavailable, never as empty)."""
    cmd = ["python3", ROOM_SCRIPT] if not m.get("ssh") else \
          ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", m["ssh"], m.get("python", "python3") + " ~/pool/room.py"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=25, stdin=subprocess.DEVNULL).stdout
        return json.loads(out)
    except Exception:
        return None


def llama_models(url):
    """Model ids a llama-server answers for, or None if it doesn't answer."""
    try:
        with urllib.request.urlopen(url.rsplit("/chat/completions", 1)[0] + "/models", timeout=4) as r:
            return [x.get("id") for x in json.load(r).get("data", [])]
    except Exception:
        return None


def headroom(m, r):
    """Bytes spare above the machine's reserve (below it is the freeze zone); -1 GiB when the GPU is busy."""
    if m.get("memory") == "gpu":
        gpus = r.get("gpus") or []
        if not gpus: return None
        g = gpus[0]
        if g.get("busy_percent", 0) >= m.get("max_busy_percent", 90): return -GiB
        return g["free_bytes"] - m["reserve_bytes"]
    avail = (r.get("memory") or {}).get("available_bytes")
    return None if avail is None else avail - m["reserve_bytes"]


class Pool:
    def __init__(self, config_dir=None, room_reader=read_room, models_reader=llama_models):
        self.config_dir = config_dir
        self.room_reader, self.models_reader = room_reader, models_reader
        self.view, self.at = {}, 0.0
        self.lock = threading.Lock()
        self.thread = None

    def refresh(self):
        """Read every machine once (in parallel) and replace the view."""
        cfg = load_config(self.config_dir)
        if cfg is None:
            with self.lock: self.view, self.at = {}, 0.0
            return
        machines, backends, tasks = cfg
        with ThreadPoolExecutor(max(1, len(machines))) as ex:
            rooms = dict(zip(machines, ex.map(self.room_reader, machines.values())))
        served = {}
        for b in backends:
            r = rooms.get(b["machine"])
            if r is None: served[id(b)] = False
            elif b.get("kind") == "lmstudio":   # LM Studio lists downloaded models too; only trust what is loaded
                served[id(b)] = b["model"] in (r.get("lmstudio_loaded") or [])
            else:
                served[id(b)] = b["model"] in (self.models_reader(b["url"]) or [])
        view = {"machines": machines, "backends": backends, "tasks": tasks, "rooms": rooms,
                "headroom": {n: (None if r is None else headroom(machines[n], r)) for n, r in rooms.items()},
                "served": served}
        with self.lock: self.view, self.at = view, time.time()

    def start(self):
        """Background refresh, once. Safe to call more than once."""
        if self.thread is not None: return
        def loop():
            while True:
                try: self.refresh()
                except Exception: pass
                time.sleep(REFRESH_S)
        self.thread = threading.Thread(target=loop, name="local-pool", daemon=True)
        self.thread.start()

    def choose(self, task, tokens=0):
        """(backends to try in order, verdicts). Best-ranked model first; within a model, machines in the order
        backends.json lists them, so a model stays on its home machine and spills to the next only when home has
        no room (Gloria 2026-11-05). Empty when the reading is stale or missing, the task is unknown, or nothing has room."""
        with self.lock: v, at = self.view, self.at
        if not v or time.time() - at > STALE_S:
            return [], [{"reason": "no fresh pool reading"}]
        if task not in v["tasks"]:
            return [], [{"reason": "unknown task %r" % task}]
        ok, verdicts = [], []
        for rank, label in enumerate(v["tasks"][task]["models"]):
            for b in [x for x in v["backends"] if x["label"] == label]:
                h = v["headroom"].get(b["machine"])
                why = None
                if v["rooms"].get(b["machine"]) is None: why = "no room report"
                elif not v["served"].get(id(b)): why = "not loaded there"
                elif h is None: why = "memory reading unknown"
                elif h < 0: why = "too full or busy"
                elif b.get("loaded_context", 0) < tokens: why = "context too small"
                verdicts.append({"model": label, "machine": b["machine"], "rank": rank + 1, "ok": why is None,
                                 "reason": why or "%.1f GiB spare" % (h / GiB)})
                if why is None: ok.append(b)
        return ok, verdicts
