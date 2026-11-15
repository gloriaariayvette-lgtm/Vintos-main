#!/usr/bin/env python3
"""k2_printer.py — her Creality K2: what is in which slot, her slicing settings, and the send.

Gloria, 14 November: "Slicing/trees/all preferred settings should be included. I prefer a layer of pla, or whatever
filament differs from the main, to be used between contact points." Her slots: PLA 1, PETG 2, carbon (PETG-CF) 3,
foaming ASA 4 once it is known to pass the CFS gears; the two TPUs feed from the external spool. All white but the
carbon fibre.

What this file does, and nothing more:
  slice(stl, material)   Creality Print 7.3 on Aegis, headless (--cli), with her settings per material taken from
                         her own K2 prints (Nov 2026: R4 PETG trees, R12 PETG-CF with contact interfaces, the haptic
                         box PLA, the R24 TPU, the R26 Siraya Air foaming TPU). Tree supports, slim; the contact
                         layers under a part are the other filament; a prime tower when there are two.
  preflight / send       Moonraker (port 7125) uploads the file; the K2's own socket (port 9999) gets the slot map
                         and the start, exactly as Creality Print's printer page sends them (colorMatch, then
                         multiColorPrint; the external spool is a plain print).
It never starts anything by itself: print_lane.py calls send() only after her Yes on her phone.

The printer's address is not in this file (the repository is public): memory/k2-printer.json holds {"host": ...}.

    python3 k2_printer.py              the printer, the box and the slots, now
    python3 k2_printer.py slice <stl> <material>
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "k2-printer.json")
SLOTS_FILE = os.path.join(MEMORY, "k2-filaments.json")

BUILD_MM = (256, 256, 256)        # K2 build volume (260 mm cube), less a margin for the brim
GCODES = "/mnt/UDISK/printer_data/gcodes/"   # where Moonraker's uploads sit on the printer

# What she keeps on hand and where (14 November). Slot ids are the CFS's own: box 1, ports A-D.
DEFAULT_SLOTS = {
    "slots": [
        {"slot": 1, "id": "T1A", "box": 1, "port": 0, "material": "PLA", "color": "#FFFFFF"},
        {"slot": 2, "id": "T1B", "box": 1, "port": 1, "material": "PETG", "color": "#FFFFFF"},
        {"slot": 3, "id": "T1C", "box": 1, "port": 2, "material": "PETG-CF", "color": "#32646D"},
        {"slot": 4, "id": "T1D", "box": 1, "port": 3, "material": "ASA", "color": "#FFFFFF", "confirmed": False,
         "note": "foaming ASA, unopened; slot 4 only if it feeds through the CFS without jamming the gears"},
    ],
    "external": [
        {"material": "TPU", "color": "#FFFFFF", "note": "CR-TPU, external spool"},
        {"material": "FOAMING-TPU", "color": "#FFFFFF", "note": "Siraya Tech TPU Air 85A, external spool"},
    ],
    "said": "Gloria, 14 November",
}

# Her settings, per material, from her own prints on this K2. base: Creality's system process / filament preset the
# override starts from; process / filament: what she changed. interface: the contact-layer filament (another slot).
COMMON_SUPPORT = {"enable_support": "1", "support_type": "tree(auto)", "support_style": "tree_slim",
                  "support_threshold_angle": "35", "support_on_build_plate_only": "0",
                  "support_interface_top_layers": "2", "support_interface_bottom_layers": "0",
                  "support_interface_spacing": "0.5", "support_interface_pattern": "rectilinear",
                  "support_base_pattern": "rectilinear", "independent_support_layer_height": "1",
                  "seam_position": "aligned", "top_shell_layers": "5", "bottom_shell_layers": "5",
                  "curr_bed_type": "Textured PEI Plate"}
PROFILES = {
    "PLA": {"from": "haptic box PLA (11 Nov)", "where": "cfs", "interface": "PETG",
            "process_base": "0.20mm Standard", "filament_base": "CR-PLA",
            "process": {"layer_height": "0.2", "wall_loops": "3", "sparse_infill_density": "20%",
                        "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": "3",
                        "outer_wall_speed": "40", "support_top_z_distance": "0.2"},
            "filament": {"nozzle_temperature": ["220"], "textured_plate_temp": ["50"], "hot_plate_temp": ["50"]}},
    "PETG": {"from": "R4 middle ring, RoboParty CR-PETG (6 Nov)", "where": "cfs", "interface": "PLA",
             "process_base": "0.16mm Standard", "filament_base": "CR-PETG",
             "process": {"layer_height": "0.16", "wall_loops": "5", "sparse_infill_density": "35%",
                         "sparse_infill_pattern": "grid", "brim_type": "outer_only", "brim_width": "6",
                         "outer_wall_speed": "60", "support_top_z_distance": "0.2"},
             "filament": {"nozzle_temperature": ["250"], "textured_plate_temp": ["70"], "hot_plate_temp": ["70"],
                          "filament_max_volumetric_speed": ["18"]}},
    "PETG-CF": {"from": "R12 CF frame, contact interfaces with removal gap (8 Nov)", "where": "cfs", "interface": "PLA",
                "process_base": "0.20mm Standard", "filament_base": "Generic PETG-CF",
                "process": {"layer_height": "0.2", "wall_loops": "5", "sparse_infill_density": "40%",
                            "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": "10",
                            "outer_wall_speed": "35", "support_top_z_distance": "0.3"},
                "filament": {"nozzle_temperature": ["250"], "textured_plate_temp": ["70"], "hot_plate_temp": ["70"],
                             "filament_max_volumetric_speed": ["8"]}},
    # ASA's contact layers are PETG: the slicer refuses ASA with PLA (too far apart in temperature, 14 November).
    "ASA": {"from": "Creality's ASA preset; foaming ASA not yet printed here", "where": "cfs", "interface": "PETG",
            "process_base": "0.20mm Standard", "filament_base": "Generic ASA",
            "process": {"layer_height": "0.2", "wall_loops": "4", "sparse_infill_density": "30%",
                        "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": "8",
                        "outer_wall_speed": "40", "support_top_z_distance": "0.2"},
            "filament": {}},
    "TPU": {"from": "R24 CR-TPU zero-retraction (10 Nov)", "where": "external", "interface": None,
            "process_base": "0.16mm Standard", "filament_base": "CR-TPU",
            "process": {"layer_height": "0.15", "wall_loops": "4", "sparse_infill_density": "25%",
                        "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": "10",
                        "outer_wall_speed": "15", "inner_wall_speed": "15", "sparse_infill_speed": "15",
                        "support_top_z_distance": "0.3", "retraction_length": "0.8", "z_hop": "0.4"},
            "filament": {"nozzle_temperature": ["220"], "nozzle_temperature_initial_layer": ["230"],
                         "textured_plate_temp": ["40"], "hot_plate_temp": ["40"],
                         "filament_max_volumetric_speed": ["1.5"], "filament_retraction_length": ["0"]}},
    "FOAMING-TPU": {"from": "R26 Siraya TPU Air 85A, 270 C, 50% flow, no retract (12 Nov)", "where": "external",
                    "interface": None, "process_base": "0.20mm Standard", "filament_base": "CR-TPU",
                    "process": {"layer_height": "0.2", "wall_loops": "4", "sparse_infill_density": "25%",
                                "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": "10",
                                "outer_wall_speed": "30", "inner_wall_speed": "30", "sparse_infill_speed": "30",
                                "support_top_z_distance": "0.3", "retraction_length": "0", "z_hop": "0.4"},
                    "filament": {"nozzle_temperature": ["270"], "nozzle_temperature_initial_layer": ["270"],
                                 "textured_plate_temp": ["40"], "hot_plate_temp": ["40"],
                                 "filament_max_volumetric_speed": ["3"], "filament_flow_ratio": ["0.5"],
                                 "filament_retraction_length": ["0"]}},
}
ALIASES = {"PLA": "PLA", "PETG": "PETG", "CR-PETG": "PETG", "PETG-CF": "PETG-CF", "CARBON": "PETG-CF", "CF": "PETG-CF",
           "ASA": "ASA", "FOAMING-ASA": "ASA", "TPU": "TPU", "FOAMING-TPU": "FOAMING-TPU", "TPU-AIR": "FOAMING-TPU",
           "FOAMING TPU": "FOAMING-TPU", "FOAMING ASA": "ASA"}


def material_of(text):
    t = re.sub(r"[\s_]+", "-", str(text or "").strip().upper())
    return ALIASES.get(t) or ALIASES.get(t.replace("-", " ")) or ""


def _cfg():
    try:
        return json.load(open(CONFIG))
    except Exception:
        return {}


def slots():
    try:
        d = json.load(open(SLOTS_FILE))
        if isinstance(d, dict) and d.get("slots"):
            return d
    except Exception:
        pass
    return DEFAULT_SLOTS


def slot_for(material, inv=None):
    """The slot row holding this material, or the external row, or None."""
    inv = inv or slots()
    for s in inv.get("slots", []):
        if material_of(s.get("material")) == material:
            return s
    for e in inv.get("external", []):
        if material_of(e.get("material")) == material:
            return dict(e, slot="external")
    return None


def on_hand(inv=None):
    """One line per material, for him and for her."""
    inv = inv or slots()
    out = []
    for s in inv.get("slots", []):
        out.append("slot %d: %s%s%s" % (s["slot"], s["material"], " (carbon fibre)" if s["material"] == "PETG-CF" else ", white",
                                       "" if s.get("confirmed", True) else " — not yet confirmed: " + s.get("note", "")))
    for e in inv.get("external", []):
        out.append("external spool: %s, white" % e["material"].lower().replace("-", " "))
    return out


# ------------------------------------------------------------------ slicing (Creality Print 7.3 on Aegis, headless)

def _exe():
    c = _cfg().get("slicer")
    if c and os.path.exists(c):
        return c
    found = sorted(glob.glob("/mnt/c/Program Files/Creality/Creality Print */CrealityPrint.exe"))
    return found[-1] if found else ""


def _system_dir():
    c = _cfg().get("presets")
    if c and os.path.isdir(c):
        return c
    found = sorted(glob.glob("/mnt/c/Users/*/AppData/Roaming/Creality/Creality Print/*/system/Creality"))
    return found[-1] if found else ""


def _win(path):
    r = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() or path


def _preset(kind, base, overrides, name):
    """Creality's own system preset for the K2 with her values put in: the slicer refuses a user preset whose
    printer list does not carry over, so the file keeps the system preset's shape and only her keys change."""
    sysd = _system_dir()
    src = os.path.join(sysd, kind, "%s @Creality K2 0.4 nozzle.json" % base)
    d = json.load(open(src))
    d.update(overrides)
    d["name"] = d.get("name")    # unchanged: the printer list matches by name
    return d


def stl_bounds(path):
    """(min xyz, max xyz) of a binary or ASCII STL, or None."""
    import struct
    try:
        data = open(path, "rb").read()
    except OSError:
        return None
    pts = []
    if len(data) > 84 and 84 + 50 * struct.unpack("<I", data[80:84])[0] == len(data):     # binary: the count fits
        n = struct.unpack("<I", data[80:84])[0]
        for i in range(n):
            off = 84 + i * 50 + 12
            for j in range(3):
                pts.append(struct.unpack("<3f", data[off + 12 * j: off + 12 * j + 12]))
    else:
        for m in re.finditer(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data):
            pts.append(tuple(float(x) for x in m.groups()))
    if not pts:
        return None
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def slice(stl, material, outdir, supports=True, runner=None):
    """Her settings for this material; a G-code file on Aegis. {ok, gcode, minutes, grams, tools, interface, why}."""
    material = material_of(material)
    prof = PROFILES.get(material)
    if not prof:
        return {"ok": False, "why": "no profile for %r; she keeps %s" % (material, ", ".join(PROFILES))}
    exe, sysd = _exe(), _system_dir()
    if not exe or not sysd:
        return {"ok": False, "why": "Creality Print is not found on Aegis"}
    b = stl_bounds(stl)
    if not b:
        return {"ok": False, "why": "the model is not a readable STL"}
    size = [hi - lo for lo, hi in zip(*b)]
    if any(s > m for s, m in zip(size, BUILD_MM)) or min(size) <= 0.2:
        return {"ok": False, "why": "the model is %s mm; the K2 takes up to %s mm" % (
            " x ".join("%.0f" % s for s in size), " x ".join(str(m) for m in BUILD_MM))}
    os.makedirs(outdir, exist_ok=True)
    interface = prof["interface"] if supports else None
    process = dict(COMMON_SUPPORT); process.update(prof["process"])
    if not supports:
        process["enable_support"] = "0"
    fils = [_preset("filament", prof["filament_base"], prof["filament"], material)]
    if interface:
        ip = PROFILES[interface]
        fils.append(_preset("filament", ip["filament_base"], ip["filament"], interface))
        process.update({"support_filament": "1", "support_interface_filament": "2", "enable_prime_tower": "1",
                        "prime_tower_width": "60", "flush_volumes_matrix": ["0", "400", "400", "0"]})
    else:
        process.update({"support_filament": "0", "support_interface_filament": "0", "enable_prime_tower": "0"})
    proc = _preset("process", prof["process_base"], process, material)
    paths = []
    for i, d in enumerate([proc] + fils):
        p = os.path.join(outdir, "preset-%d.json" % i)
        json.dump(d, open(p, "w"), indent=1); paths.append(p)
    machine = os.path.join(sysd, "machine", "Creality K2 0.4 nozzle.json")
    out = os.path.join(outdir, "sliced"); os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*")):
        os.remove(f)
    cmd = [exe, "--cli", "--slice", "0", "--need-gcode-file", "--outputdir", _win(out),
           "--load-settings", _win(machine) + ";" + _win(paths[0]),
           "--load-filaments", ";".join(_win(p) for p in paths[1:]), _win(stl)]
    r = (runner or subprocess.run)(cmd, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    with open(os.path.join(outdir, "slicer.log"), "w") as f:
        f.write(log[-200000:])
    gs = sorted(glob.glob(os.path.join(out, "*.gcode")))
    if not gs:
        err = [l for l in log.splitlines() if re.search(r"(?i)not compatible|failed|invalid|error code", l)]
        return {"ok": False, "why": "the slicer made no G-code: %s" % ((err[-1] if err else "no reason given")[-200:])}
    return dict(read_gcode(gs[0]), ok=True, gcode=gs[0], material=material,
                interface=interface, size_mm=[round(s, 1) for s in size])


def read_gcode(path):
    """Time, grams per filament and which tools the file uses, from its own header."""
    with open(path, errors="replace") as f:
        head = f.read(400000)
        f.seek(0, 2); size = f.tell()
    with open(path, "rb") as f:     # Creality writes the time, grams and settings at the end
        f.seek(max(0, size - 600000)); head += "\n" + f.read().decode("utf8", "replace").replace("\r\n", "\n")
    t = re.search(r"^; estimated printing time \(normal mode\) = (.+)$", head, re.M)
    g = re.search(r"^; filament used \[g\] = (.+)$", head, re.M)
    mins = 0.0
    if t:
        for n, u in re.findall(r"(\d+)\s*([dhms])", t.group(1)):
            mins += int(n) * {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}[u]
    grams = [float(x) for x in re.findall(r"[\d.]+", g.group(1))] if g else []
    tools = set()
    with open(path, errors="replace") as f:
        for line in f:
            m = re.match(r"T(\d+)\s*$", line)
            if m:
                tools.add(int(m.group(1)))
    thumb = re.search(r"; thumbnail begin \d+x\d+ \d+\n((?:; .*\n)+?); thumbnail end", head)
    return {"minutes": round(mins, 1), "time": t.group(1).strip() if t else "", "grams": grams,
            "tools": sorted(tools) or [0], "has_thumbnail": bool(thumb)}


def thumbnail(gcode, out_png):
    import base64
    head = open(gcode, errors="replace").read(400000)
    m = re.search(r"; thumbnail begin \d+x\d+ \d+\n((?:; .*\n)+?); thumbnail end", head)
    if not m:
        return ""
    data = base64.b64decode("".join(l[2:].strip() for l in m.group(1).splitlines()))
    open(out_png, "wb").write(data)
    return out_png


# ------------------------------------------------------------------ the printer

def host():
    return str(_cfg().get("host") or "")


def _http(method, path, timeout=20, **kw):
    import requests
    h = host()
    if not h:
        raise RuntimeError("no printer address in memory/k2-printer.json")
    return getattr(requests, method)("http://%s:7125%s" % (h, path), timeout=timeout, **kw)


def _socket(messages, wait_for=(), seconds=8):
    """Send these to the K2's own socket; the replies whose keys are in wait_for, as one dict."""
    import asyncio
    import websockets

    async def run():
        got = {}
        async with websockets.connect("ws://%s:9999" % host(), open_timeout=8) as ws:
            for m in messages:
                await ws.send(json.dumps(m))
            try:
                async with asyncio.timeout(seconds):
                    async for raw in ws:
                        try:
                            d = json.loads(raw)
                        except Exception:
                            continue
                        if isinstance(d, dict):
                            for k in d:
                                got.setdefault(k, d[k])
                        if wait_for and all(k in got for k in wait_for):
                            break
            except TimeoutError:
                pass
        return got
    return asyncio.run(run())


def status():
    """What the K2 says now: {reachable, state, file, cfs_connected, box: [{slot, type, color}], external}."""
    out = {"reachable": False}
    try:
        st = _http("get", "/printer/objects/query?print_stats", timeout=8).json()["result"]["status"]["print_stats"]
        out.update(reachable=True, state=st.get("state", ""), file=st.get("filename", ""))
    except Exception as e:
        out["why"] = str(e)[:120]
        return out
    try:
        d = _socket([{"method": "get", "params": {"boxsInfo": 1}}], wait_for=("boxsInfo", "cfsConnect"))
        out["cfs_connected"] = int(d.get("cfsConnect") or 0) == 1
        box, ext = [], []
        for b in (d.get("boxsInfo") or {}).get("materialBoxs", []):
            for m in b.get("materials", []):
                row = {"type": m.get("type", ""), "color": m.get("color", ""), "name": m.get("name", "")}
                if b.get("type") == 1:
                    ext.append(row)
                else:
                    box.append(dict(row, slot=int(m.get("id", 0)) + 1, box=int(b.get("id", 1))))
        out["box"], out["external"] = box, ext
    except Exception as e:
        out["box_why"] = str(e)[:120]
    return out


def preflight(job, st=None):
    """(ok, why) just before a send: the printer is idle, and the slots it needs hold what the file was sliced for."""
    st = st or status()
    if not st.get("reachable"):
        return False, "the K2 did not answer (%s)" % st.get("why", "")
    if st.get("state") not in ("standby", "complete", "cancelled", "error", ""):
        return False, "the K2 is %s (%s)" % (st.get("state"), st.get("file") or "")
    if job.get("where") == "cfs":
        if not st.get("cfs_connected"):
            return False, "the CFS box reads as disconnected"
        for s in job.get("slots", []):
            seen = next((b for b in st.get("box", []) if b.get("slot") == s["slot"]), None)
            if seen and seen.get("type") and material_of(seen["type"]) and material_of(seen["type"]) != material_of(s["material"]):
                return False, "slot %d reads %s, not %s" % (s["slot"], seen["type"], s["material"])
    return True, ""


def upload(gcode, name):
    with open(gcode, "rb") as f:
        r = _http("post", "/server/files/upload", timeout=600, files={"file": (name, f, "application/octet-stream")},
                  data={"root": "gcodes"})
    if r.status_code >= 300:
        raise RuntimeError("upload refused (%s)" % r.status_code)
    return GCODES + name


def start(path, job, socket_send=None):
    """The slot map, then the start, as Creality Print's printer page sends them. Then wait to see it printing."""
    send = socket_send or (lambda msgs: _socket(msgs, seconds=6))
    if job.get("where") == "cfs":
        match = [{"id": s["id"], "type": s["material"].replace("FOAMING-", ""), "color": s.get("color", "#FFFFFF"),
                  "boxId": s.get("box", 1), "materialId": s.get("port", 0)} for s in job["slots"]]
        send([{"method": "set", "params": {"colorMatch": {"path": path, "list": match}}}])
        send([{"method": "set", "params": {"multiColorPrint": {"gcode": path, "enableSelfTest": 0}}}])
    else:
        send([{"method": "set", "params": {"opGcodeFile": "printprt:" + path, "enableSelfTest": 0}}])
    return True


def printing(name, tries=12, pause=5, st=None):
    for _ in range(tries):
        s = st() if st else status()
        if s.get("state") == "printing" and os.path.basename(str(s.get("file", ""))) == name:
            return True
        time.sleep(pause)
    return False


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[1] == "slice":
        print(json.dumps(slice(sys.argv[2], sys.argv[3], os.path.join(MEMORY, "k2-print", "manual")), indent=1))
    else:
        print("\n".join(on_hand()))
        print(json.dumps(status(), indent=1))
