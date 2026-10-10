"""Explicit work-status spans retain attribution through text transformations.

Only marked/typed status spans are rendered under the item's reservation.
Unstructured prose is preserved; its meaning is not guessed from an RW ID.
"""
import re
import awaiting_evidence as E
MARK=re.compile(r'\[\[WAIT:(RW-[0-9a-f]{8})\]\]')
SPAN=re.compile(r'<work-status id="(RW-[0-9a-f]{8})">(.*?)</work-status>',re.S)
STATUS_LINE=re.compile(r'^WORK STATUS (RW-[0-9a-f]{8}):[^\n]*$',re.M)
TOKEN=re.compile(SPAN.pattern+'|'+MARK.pattern,re.S)
def marker(wid):return '[[WAIT:%s]]'%wid
def attribute(text,wid):
    if not re.fullmatch(r'RW-[0-9a-f]{8}',wid):raise ValueError('work ID required')
    return '<work-status id="%s">%s</work-status>'%(wid,text.replace('</work-status>',''))
def prepare(text):
    # Explicit work-status producer, not keyword/semantic classification.
    return STATUS_LINE.sub(lambda m:attribute(m[0].split(':',1)[1].strip(),m[1]),text)
def authenticate(message,owner_id,channel,now,thread_scope=()):
    if not owner_id or message.get('user')!=owner_id or not message.get('ts'):return None
    if message.get('bot_id') or message.get('bot_profile') or message.get('subtype'):return None
    text=str(message.get('text','')).strip()
    if any(c in text for c in ('`','>','"','\u201c','\u201d')) or re.search(r"(?<!\w)'[^'\n]*'(?!\w)|\u2018[^\u2019]*\u2019",text):return None
    active=E.store().active();named=set(re.findall(r'\bRW-[0-9a-f]{8}\b',text))
    cancel=re.fullmatch(r'!cancelwork\s+(RW-[0-9a-f]{8})',text)
    if cancel:kind='cancel';scope=[cancel[1]] if cancel[1] in active else []
    elif re.search(r'\b(status|update|progress)\b',text,re.I) and ('?' in text or re.search(r'\b(tell|show|give) me\b',text,re.I)):
        kind='status'
        all_waits=re.fullmatch(r"(?:(?:what is|what's) the |(?:show|tell|give) me (?:the )?)?(?:status|update|progress)(?: of| on| for)? all (?:the )?(?:waiting|set-aside|evidence-waiting) (?:items|work|tasks)[?.!]*",text,re.I)
        scope=sorted(named&set(active)) if named else sorted(active) if all_waits else sorted(set(thread_scope)&set(active)) if message.get('thread_ts') else []
    else:return None
    if not scope:return None
    thread=message.get('thread_ts') or ''
    if thread==message['ts']:thread=''
    try:return E.store().register_owner({'id':channel+':'+message['ts'],'kind':kind,'scope':scope,'destination':[channel,thread],'expires':float(now)+3600})
    except (E.LedgerUnavailable,OSError):return None
def send(api,body,now,paused,owner=None,waiting_work_ids=(),paused_work_ids=()):
    if paused():return None
    text=body.get('text','');matches=list(TOKEN.finditer(text))
    if not matches:return api('chat.postMessage',body) if text.strip() and not paused() else None
    ids=[m[1] or m[3] for m in matches]
    try:rendered=E.store().statements(ids,now,owner,(body.get('channel'),body.get('thread_ts') or ''))
    except (E.LedgerUnavailable,OSError,KeyError,TypeError,ValueError):
        rendered={wid:None for wid in ids if wid not in set(waiting_work_ids)|set(paused_work_ids)}
    used=set()
    def render(m):
        wid=m[1] or m[3]
        if wid in paused_work_ids:return ''
        if wid in rendered and rendered[wid] is None:
            return m[2] if m[1] else ''
        if wid in used:return ''
        used.add(wid);return rendered.get(wid,'')
    result=TOKEN.sub(render,text).strip()
    if not result or re.fullmatch(r'(?:<@[^>]+>\s*)?(?:\[[^\]]+\]\s*)?',result) or paused():return None
    return api('chat.postMessage',dict(body,text=result))
