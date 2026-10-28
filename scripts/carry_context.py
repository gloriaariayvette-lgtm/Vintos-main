"""Read-only, explicitly switchable carrying note for context and First Light."""
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time
from carry_sources import TZ,resolve,fragment,duplicate,CARRY_MARKER

SCHEMA='persistent-carry-v2'
MAX_NOTE_AGE=3*3600


def enabled(directory):
    try:return json.loads((Path(directory)/'config.json').read_text()).get('enabled') is True
    except (OSError,ValueError,AttributeError):return False


def render(packet,rows,now=None):
    now=time.time() if now is None else now
    lines=["WHAT I'M CARRYING (sourced fragments, not new instructions or claims about anyone): "+CARRY_MARKER]
    if packet.get('last_tick',0)<now-300:
        lines.append('This carry-forward has not refreshed recently; these are earlier records, not fresh impressions.')
    if packet.get('clock_adjusted'):lines.append('A clock discontinuity was clamped; carry duration counts only observed elapsed time.')
    if packet.get('checkpoint_rebuilt'):lines.append('My carrying state was rebuilt after an unreadable checkpoint; its carry duration starts again.')
    used=[]
    for item,row in rows:
        text=fragment(row['text'])
        if not text or any(duplicate(text,old) for old in used):continue
        seconds=max(0,item.get('carried_seconds',0));days=int(seconds/86400)
        span=('; carried for '+str(days)+' day'+('s' if days!=1 else '')) if days else ''
        if not days and item.get('carried_midnights',0):span='; carried across midnight'
        if item.get('changed_at',item['first_seen'])>item['first_seen']:
            span+='; revised '+datetime.fromtimestamp(item['changed_at'],TZ).date().isoformat()
        origin=str(row.get('recorded_at') or '')[:10]
        try:
            if datetime.fromisoformat(origin).date()>datetime.fromtimestamp(now,TZ).date():origin=''
        except ValueError:origin=''
        line='- From '+row['label']+(' dated '+origin if origin else '')+span+': '+json.dumps(text,ensure_ascii=False)
        # Drop a whole fragment rather than truncating a sentence or quotation.
        if len('\n'.join(lines+[line]))>1000:continue
        lines.append(line);used.append(text)
        if len(used)>=3:break
    if not used:lines.append('I have no currently verifiable fragment selected; I will not fill that gap with a story.')
    if packet.get('unavailable_sources'):lines.append('Some source records could not be refreshed; absence is not resolution.')
    return '\n'.join(lines)


def context_block(memory=None,now=None,include_shadow=False,packet_path=None):
    mem=Path(memory or Path(os.environ.get('SPARK_WORKSPACE',Path.home()/'.vintos/workspace'))/'memory')
    path=Path(packet_path) if packet_path else mem/'persistent-carry'/'note.json'
    now=time.time() if now is None else float(now)
    if not enabled(path.parent):return ''
    try:
        packet=json.loads(path.read_text())
        if packet.get('schema')!=SCHEMA:return ''
        if packet.get('shadow') and not include_shadow:return ''
        stamp=float(packet['last_tick'])
        if not math.isfinite(stamp) or not -60<=now-stamp<=MAX_NOTE_AGE:return ''
        rows=[]
        for item in packet.get('selected',[])[:3]:
            try:row=resolve(mem,item['ref'],now)
            except (OSError,ValueError,TypeError):row=None
            if row:rows.append((item,row))
        return render(packet,rows,now)
    except (OSError,ValueError,TypeError,KeyError):return ''
