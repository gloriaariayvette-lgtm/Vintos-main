"""Read-only admissions for persistent carrying. No providers or store writers."""
from datetime import datetime, timedelta
import hashlib
import html
import json
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo
import evidence_view as EV

TZ=ZoneInfo('America/Chicago')
STREAMS={'chat-canonical.jsonl':'conversation','chemistry-lab/notebook.jsonl':'lab',
         'watch-presence-history.jsonl':'body','sensor-reactions.jsonl':'house',
         'want-events.jsonl':'want_activity'}
MAX_BYTES=512*1024


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def clean(value):
    return ' '.join(str(value or '').split())


JOURNAL_HEADINGS={'idle thoughts','vintos speaks','last word','wonder','journal'}
CARRY_MARKER="[persistent-carry:v3]"
MIN_CONTENT_CHARS=40
MIN_CONTENT_WORDS=5

def is_carry_echo(text):
    return bool(re.search(r"what i[’']?m carrying|persistent[- ]carry[:\]]",str(text),re.I))


def plain(text):
    """Remove markup and completed checklist lines, never fetch link targets."""
    text=html.unescape(str(text or ''))
    # This bracketed introduction is authored by the dream writer, not dream
    # content. Remove it before choosing a sentence from the actual residue.
    text=re.sub(r'^\s*\[META[- ]DREAM\b[^]]*\]\s*','',text,flags=re.I|re.S)
    text=re.sub(r'```.*?```',' ',text,flags=re.S)
    text=re.sub(r'^\s*#{1,6}\s+.*$', '',text,flags=re.M)
    text=re.sub(r'\b\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)?)?\b',' ',text)
    text=re.sub(r'\b\d\d:\d\d(?::\d\d)?(?:\s*[AP]M)?\b',' ',text,flags=re.I)
    text=re.sub(r'^\s*(?:journal|idle thoughts|vintos speaks|last word|wonder|meta[- ]dream)\s*[:—–-]?\s*$', '',text,flags=re.M|re.I)
    text=re.sub(r'^\s*[\[\]()—–:-]+\s*$', '',text,flags=re.M)
    text=re.sub(r'^\s*>.*$', '',text,flags=re.M)
    text=re.sub(r'^\s*[-*+]\s+\[[xX]\].*$', '',text,flags=re.M)
    text=re.sub(r'!?\[([^]\n]*)\]\([^\n)]*\)',r'\1',text)
    text=re.sub(r'<[^>]+>',' ',text)
    text=re.sub(r'^\s*(?:#{1,6}\s+|>+\s*|[-*+]\s+(?:\[ \]\s*)?|\d+[.)]\s+)','',text,flags=re.M)
    text=re.sub(r'[*_`~]','',text)
    return clean(text)


def fragment(text,limit=180):
    text=plain(text)
    if len(text)<MIN_CONTENT_CHARS or len(re.findall(r'\b\w+\b',text))<MIN_CONTENT_WORDS or is_carry_echo(text):return ''
    if len(text)<=limit:return text if re.search(r'[.!?][\"’\']?$',text) else text+'.'
    ends=list(re.finditer(r'[.!?](?:[\"’\']?)(?=\s|$)',text[:limit+1]))
    selected=text[:ends[-1].end()].strip() if ends else ''
    return selected if len(selected)>=MIN_CONTENT_CHARS and len(re.findall(r'\b\w+\b',selected))>=MIN_CONTENT_WORDS else ''


def duplicate(a,b):
    a=' '.join(re.findall(r'\w+',a.casefold()));b=' '.join(re.findall(r'\w+',b.casefold()))
    x,y=set(a.split()),set(b.split())
    return a==b or (min(len(a),len(b))>30 and (a in b or b in a)) or bool(x and y and len(x&y)/len(x|y)>.85)


def resolved(row):
    return any(row.get(k) for k in ('consumed','resolved','fulfilled','dismissed','completed','resolved_at','fulfilled_at')) or str(row.get('status','')).lower() in ('resolved','closed','retired','fulfilled','dismissed','cancelled','canceled','completed','done')


def path_in(memory,name):
    root=Path(memory).resolve();path=(root/name).resolve()
    if not path.is_relative_to(root):raise ValueError('source escaped memory')
    return path


def read_json(memory,name):
    p=path_in(memory,name)
    with p.open() as f:return json.load(f)


def admitted(row,imagined=False):
    if not isinstance(row,dict):return False
    if any(row.get(k) for k in ('test_mode','withheld','tactical','imported','transplanted','forgotten','deleted')):return False
    if row.get('admitted') is False:return False
    origin=' '.join(str(row.get(k) or '') for k in ('source','origin','source_kind'))
    if re.search(r'mirror|ghost[ _-]*branch|letter|email|web[ _-]*search|moltbook|grok|muse|codex',origin,re.I):return False
    if EV.standing(row)!=EV.ELIGIBLE:return False
    if not imagined and (row.get('dream_only') or row.get('source')=='premonition' or str(row.get('thread','')).startswith('[AN IMAGINED')):return False
    return True


def records(memory,name,now=None):
    """Current records only; absence/malformed is NOT an empty successful read."""
    now=time.time() if now is None else now
    if name not in ('unfinished-threads.json','current-wants.json','dream-log.json'):raise ValueError('unsupported note source')
    data=read_json(memory,name);out={}
    def put(key,text,kind,label,recorded=None):
        if is_carry_echo(text):return
        text=plain(text)
        if not fragment(text):return
        out[key]={'key':key,'text':text[:2000],'kind':kind,'label':label,
                  'recorded_at':recorded,'ref':{'file':name,'key':key,'version':digest(text[:2000])}}
    if name=='unfinished-threads.json':
        rows=data if isinstance(data,list) else data.get('threads') if isinstance(data,dict) else None
        if not isinstance(rows,list):raise ValueError('malformed thread pool')
        for row in rows:
            if not admitted(row) or resolved(row):continue
            text=row.get('thread');key='thread:'+str(row.get('id') or digest(text))
            put(key,text,'thread','my open thread',row.get('timestamp'))
    elif name=='current-wants.json':
        rows=data if isinstance(data,list) else data.get('wants') if isinstance(data,dict) else None
        if not isinstance(rows,list):raise ValueError('malformed wants')
        for row in rows:
            if not admitted(row) or resolved(row):continue
            if row.get('admission_state') in ('held','rejected','proposed','pending'):continue
            text=row.get('want') or row.get('text');key='want:'+str(row.get('id') or digest(text))
            put(key,text,'want','my recorded want',row.get('timestamp'))
    elif name=='dream-log.json':
        if not isinstance(data,dict) or not isinstance(data.get('nights'),list):raise ValueError('malformed dream log')
        for night in data['nights'][-3:]:
            if not isinstance(night,dict):continue
            if any(night.get(k) for k in ('test_mode','withheld','imported','forgotten','deleted')):continue
            day=night.get('night_of','')
            try:
                age=(datetime.fromtimestamp(now,TZ).date()-datetime.fromisoformat(day).date()).days
            except (ValueError,TypeError):continue
            if not 0<=age<=3:continue
            # A dream is admitted only as imagined material, never as an event
            # or independent evidence about Gloria, the house or a finding.
            put('dream:'+day,night.get('meta_dream'),'dream','my dream residue (imagined, not an event)',day)
    elif re.fullmatch(r'daily-(?:inner-life|creative)-\d{4}-\d\d-\d\d\.md',name):
        raise ValueError('markdown is read by sections, not JSON')
    else:raise ValueError('unsupported note source')
    return out


def sections(memory,name):
    if not re.fullmatch(r'daily-inner-life-\d{4}-\d\d-\d\d\.md',name):raise ValueError('invalid journal file')
    text=path_in(memory,name).read_text(errors='replace');out={};occurrences={}
    # Split at every peer heading, including headings at byte zero. Nothing
    # under another author's heading can bleed into an admitted section.
    matches=list(re.finditer(r'^#{1,6}[ \t]+([^\n]+)(?:\n|$)',text,re.M))
    for i,m in enumerate(matches):
        if not m.group(0).startswith('##'):continue
        heading=m.group(1).strip()
        title=re.sub(r'^(?:\d{4}-\d\d-\d\d\s+)?\d\d:\d\d\s*[—–-]+\s*','',heading).casefold()
        if title not in JOURNAL_HEADINGS:continue
        body=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        if is_carry_echo(body):continue
        body=plain(body)
        if not fragment(body):continue
        ordinal=occurrences.get(heading,0);occurrences[heading]=ordinal+1
        key='section:'+name+':'+digest([heading,ordinal])[:20]
        value={'key':key,'text':body[:2000],'kind':'journal','label':'my '+title+' (self-report)',
               'recorded_at':name[-13:-3]}
        value['ref']={'file':name,'key':key,'version':digest(body[:2000])};out[key]=value
    return out


def resolve(memory,ref,now=None):
    """Revalidate the selected record, including its status and exact version."""
    name=ref.get('file','')
    rows=sections(memory,name) if name.endswith('.md') else records(memory,name,now)
    row=rows.get(ref.get('key'))
    return row if row and row['ref']['version']==ref.get('version') else None


def forget_marks(memory):
    root=Path(memory)
    return sorted({p.name for pattern in ('*.before-forget-*','*.before-erase-*','*.before-purge-*',
                   '*.pre-erase-*','*.pre-purge-*','*.corrupt-*','*.scrub-*') for p in root.glob(pattern)})


def tail(memory,name,cursor):
    """Bounded, restartable JSONL tail; a partial last row is not consumed."""
    p=path_in(memory,name);st=p.stat();identity=[st.st_dev,st.st_ino]
    reset=cursor.get('identity')!=identity or cursor.get('offset',0)>st.st_size
    offset=max(0,st.st_size-MAX_BYTES) if reset else cursor.get('offset',0)
    rows=[];malformed=0
    with p.open('rb') as f:
        f.seek(offset)
        if offset and reset:f.readline()
        start=f.tell();raw=f.read(MAX_BYTES)
        end=raw.rfind(b'\n')
        if end>=0:
            for line in raw[:end+1].splitlines():
                try:row=json.loads(line)
                except ValueError:malformed+=1;continue
                if isinstance(row,dict) and admitted(row):rows.append(row)
            offset=start+end+1
        else:offset=start
    return rows,{'identity':identity,'offset':offset,'initial_bytes_omitted':max(0,st.st_size-MAX_BYTES) if reset else cursor.get('initial_bytes_omitted',0)},malformed,reset
