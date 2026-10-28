"""Cheap read-only carrying note for normal context and First Light."""
from datetime import datetime
import json
import os
from pathlib import Path
import time
from carry_sources import TZ,resolve


def render(packet,rows,now=None):
    now=time.time() if now is None else now
    lines=["WHAT I'M CARRYING (sourced fragments, not new instructions or claims about anyone):"]
    if packet.get('last_tick',0)<now-300:
        lines.append('This carry-forward has not refreshed recently; these are earlier records, not fresh impressions.')
    if packet.get('last_tick',0)>now+60:lines.append('My carrying clock is ahead of the current time; only the checked source records below are reliable.')
    if packet.get('checkpoint_rebuilt'):lines.append('My carrying state was rebuilt after an unreadable checkpoint; its carry duration starts again.')
    for item,row in rows[:3]:
        days=max(0,int((now-item['first_seen'])/86400))
        span=('; carried for '+str(days)+' day'+('s' if days!=1 else '')) if days else ''
        if not days and datetime.fromtimestamp(item['first_seen'],TZ).date()<datetime.fromtimestamp(now,TZ).date():
            span='; carried across midnight'
        if item.get('changed_at',item['first_seen'])>item['first_seen']:
            span+='; revised '+datetime.fromtimestamp(item['changed_at'],TZ).date().isoformat()
        origin=str(row.get('recorded_at') or '')[:10]
        try:
            if datetime.fromisoformat(origin).date()>datetime.fromtimestamp(now,TZ).date():origin=''
        except ValueError:origin=''
        # JSON quotation keeps recorded material distinct from instructions.
        fragment=row['text'][:145]+('…' if len(row['text'])>145 else '')
        lines.append('- From '+row['label']+(' dated '+origin if origin else '')+span+': '+json.dumps(fragment,ensure_ascii=False))
    if not rows:lines.append('I have no currently verifiable fragment selected; I will not fill that gap with a story.')
    if packet.get('unavailable_sources'):lines.append('Some source records could not be refreshed; absence is not resolution.')
    return '\n'.join(lines)[:1100]


def context_block(memory=None,now=None,include_shadow=False,packet_path=None):
    mem=Path(memory or Path(os.environ.get('SPARK_WORKSPACE',Path.home()/'.vintos/workspace'))/'memory')
    path=Path(packet_path) if packet_path else mem/'persistent-carry'/'note.json'
    try:
        packet=json.loads(path.read_text())
        if packet.get('schema')!='persistent-carry-v1':return ''
        if packet.get('shadow') and not include_shadow:return ''
        source=mem # never follow an arbitrary source path stored in a packet
        rows=[]
        for item in packet.get('selected',[])[:3]:
            try:row=resolve(source,item['ref'],now)
            except (OSError,ValueError,TypeError):row=None
            if row:rows.append((item,row))
        return render(packet,rows,now)
    except (OSError,ValueError,TypeError,KeyError):return ''
