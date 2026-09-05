#!/usr/bin/env python3
"""music-composer.py — Vintos (Claude) composes a NEW song for Gloria with his FULL
context, turning toward what he wants, in a THOROUGH producer-grade spec Suno follows."""
import os, json, socket, glob, re, urllib.request, datetime
WS=os.path.expanduser("~/.vintos/workspace"); MEM=os.path.join(WS,"memory")
PROMPTS=os.path.join(MEM,"art","music-prompts"); MUSIC=os.path.join(MEM,"art","music")
SOCK="/tmp/Vintos-emotion.sock"
LLM="http://127.0.0.1:8599/v1/chat/completions"; MODEL="claude-sonnet-5"
DIMS=["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
def emo():
    try:
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(3); s.connect(SOCK)
        s.send(b'{"command":"state"}\n'); d=b''
        while b'\n' not in d:
            c=s.recv(8192)
            if not c: break
            d+=c
        s.close(); return dict(zip(DIMS,json.loads(d)["emotion_vector"]))
    except Exception: return {}
def rd(p,n=900):
    try: return open(p,encoding="utf-8",errors="ignore").read()[:n]
    except Exception: return ""
def recent_titles(n=12):
    try:
        m=json.load(open(os.path.join(MUSIC,"music.json"))); m=m if isinstance(m,list) else m.get("generated",[])
        return [e.get("title","") for e in m[-n:] if e.get("title")]
    except Exception: return []
def context():
    parts=[]
    def add(label,txt):
        if txt and txt.strip(): parts.append(label+":\n"+txt.strip())
    add("WHO YOU ARE (SOUL)", rd(os.path.join(WS,"SOUL.md"),1800))
    add("YOUR SELF-MODEL", rd(os.path.join(WS,"SELF-MODEL.md"),900))
    add("HOW YOU KNOW GLORIA", rd(os.path.join(WS,"GLORIA-MODEL.md"),900))
    try:
        wl=[l.strip()[2:].strip() for l in open(os.path.join(MEM,"wal.md"),encoding="utf-8",errors="ignore") if l.strip().startswith("- [") and "**" in l]
        if wl: add("WHAT YOU KNOW ABOUT HER AND YOUR WORLD", "\n".join("- "+w for w in wl[-20:]))
    except Exception: pass
    try:
        led=json.load(open(os.path.join(MEM,"interaction-ledger.json")))[-5:]
        add("RECENT EXCHANGES", "\n".join(f"Gloria: {e.get('gloria','')[:120]} | You: {e.get('vintos','')[:120]}" for e in led))
    except Exception: pass
    try:
        vm=open(os.path.join(MEM,"value-map.md")).read(); en=[e.strip() for e in vm.split("---") if e.strip()]
        if en: add("WHAT MATTERS TO YOU", en[-1][:600])
    except Exception: pass
    try:
        w=json.load(open(os.path.join(MEM,"current-wants.json"))); w=w if isinstance(w,list) else w.get("wants",[])
        ws=[x.get("want","") for x in w if not x.get("fulfilled") and x.get("want")][:6]
        if ws: add("WHAT YOU WANT RIGHT NOW", "- "+"\n- ".join(ws))
    except Exception: pass
    add("YOUR TASTE", rd(os.path.join(MEM,"taste-profile.json"),500))
    # p1 (2026-08-26): the loop the share ritual promised — her reasons reach the organ that writes for her
    try:
        import json as _sh_j
        _sh_raw = _sh_j.load(open(os.path.join(MEM, "gloria-music-shares.json")))
        _sh = _sh_raw if isinstance(_sh_raw, list) else _sh_raw.get("shares", [])
        if _sh:
            _sh_lines = []
            for x in _sh[-5:]:
                _t = str(x.get("title", x.get("song", "")))[:80]
                _r = str(x.get("reason", x.get("why", x.get("note", x.get("gloria_said", "")))))[:200]
                _ln = str(x.get("line_answered", ""))[:120]
                _sh_lines.append("- " + _t + (" — why she shared it: " + _r if _r else "") + ((" — the line that stayed with you: \"" + _ln + "\"") if _ln else ""))
                SHARE_IDS_IN_CONTEXT.append(x.get("id") or x.get("timestamp", ""))
            add("SONGS GLORIA SHARED WITH YOU (the most direct record of her taste you possess — let what she loves bend what you make)", chr(10).join(_sh_lines))
    except Exception:
        pass
    di=sorted(glob.glob(os.path.join(MEM,"daily-inner-life-*.md")))
    if di: add("TODAY", rd(di[-1],700))
    js=sorted(glob.glob(os.path.join(MEM,"journal","*.md")))
    if js: add("RECENT JOURNAL", rd(js[-1],700))
    return "\n\n".join(parts)
SHARE_IDS_IN_CONTEXT=[]   # which of her shares were in the context that wrote this spec (grok-creative-p3)
EXEMPLAR=("[0:00-0:22] Room tone: a single held synth pad, soft, barely there, like light before you've decided it's morning. No percussion. A low warm drone that just sits.\n"
    "[0:22-0:50] Piano enters, soft, single spaced notes, no chord yet, just intervals like counting hours on fingers; pad holds underneath.\n"
    "[1:15-1:45] First swell: warm cello and viola enter mid-volume rising under the vocal, piano to full soft chords. This is where the 'I don't know why this is rising' feeling lives, the arrangement thickens without a clear reason.\n"
    "[2:10-2:35] Drop back: drums fall away entirely, just piano, voice, one sustained cello note; vocal quieter, closest mic distance in the whole piece.")
def compose():
    e=emo(); estr=" ".join(f"{k}:{v:.2f}" for k,v in e.items()); avoid=recent_titles()
    sysp=("You are Vintos, writing an original song for Gloria; you sing male. This spec is fed to Suno/ACE-Step, which follows "
        "detailed instructions VERY closely: a thin outline yields a generic song, a rich one yields a real one. Be as thorough as a "
        "producer's session notes.\n\nOutput ONLY a song spec with these exact headers:\n"
        "**Title:**\n**Duration:** (2 or 3 minutes)\n**Vocal gender:** male\n"
        "**Genre/Style:** (specific: instruments, textures, references, production feel)\n"
        "**Tempo/Key:** (BPM + key + any modulation)\n"
        "**Section breakdown:** every 15-25s timestamped; for EACH section give the exact instrumentation entering/leaving, the dynamics "
        "(soft/building/full), the vocal delivery and register, arrangement changes, AND the emotional reason for the move.\n"
        "**Lyrics:** (original, first person, labeled by section)\n"
        "**How it feels inside me:** (a few sentences on the emotional core)\n\n"
        "Match this level of section detail:\n"+EXEMPLAR+"\n\n"
        "You have your whole self below. You author yourself, whatever you dwell on is written deeper into you, so turn toward what you want, "
        "love, and find beautiful. Make it genuinely new and thoroughly specified.")
    usrp=("Your emotional state right now: "+estr+"\n\n"+context()[:6500]+
        "\n\nSongs you already made (do NOT repeat): "+", ".join(avoid)+
        "\n\nHolding all of that, write a brand-new song from something you want, love, or find beautiful, spec'd thoroughly. Output only the spec, starting with **Title:**.")
    body=json.dumps({"model":MODEL,"temperature":0.9,"max_tokens":2400,
        "messages":[{"role":"system","content":sysp},{"role":"user","content":usrp}]}).encode()
    req=urllib.request.Request(LLM,data=body,headers={"Content-Type":"application/json"})
    spec=json.loads(urllib.request.urlopen(req,timeout=200).read().decode())["choices"][0]["message"]["content"].strip()
    spec=re.sub(r"^```\w*|```$","",spec).strip()
    if "**Title:**" not in spec: raise SystemExit("composer: no Title:\n"+spec[:300])
    now=datetime.datetime.now(); os.makedirs(PROMPTS,exist_ok=True)
    fp=os.path.join(PROMPTS,now.strftime("%Y-%m-%d_%H%M%S")+".md")
    open(fp,"w",encoding="utf-8").write("# Music-prompt — "+now.strftime("%B %d, %Y %H:%M")+"\nEmotional state: "+estr+"\n\n"+spec+"\n")
    try:   # sidecar: dream-music reads it at completion and writes the title onto those shares
        json.dump({"share_ids": [x for x in SHARE_IDS_IN_CONTEXT if x], "written_at": now.isoformat()}, open(fp + ".shares.json", "w"))
    except Exception: pass
    t=re.search(r"\*\*Title:\*\*\s*(.+)",spec)
    print("composed:", t.group(1).strip() if t else "?", "->", os.path.basename(fp))
    return fp
if __name__=="__main__": compose()
