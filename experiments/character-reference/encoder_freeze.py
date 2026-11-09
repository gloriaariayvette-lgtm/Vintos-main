"""Offline freeze qualification against reviewed, repository-owned artifact pins."""
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
import re

PIN_FILE=Path(__file__).with_name('published-encoder-pins.json')
SOURCES=('copy_time','published_artifact','legacy_unknown','unknown')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def hashed(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def instant(value):
    if isinstance(value,str):
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError('offset-aware revision date required')
        value=dt.timestamp()
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('invalid freeze clock')
    return float(value)


def pairs(items):
    out={}
    for key,value in items:
        if key in out:raise ValueError('duplicate pin field')
        out[key]=value
    return out


def validate_registry(registry):
    if (not isinstance(registry,dict) or set(registry)!={'schema','pins'} or registry['schema']!='published-encoder-pins-v1'
            or not isinstance(registry['pins'],list) or len(registry['pins'])>64):raise ValueError('invalid pin registry')
    pins={}
    fields={'id','publisher','repo','filename','revision','revision_at','artifact_sha256','artifact_kind','trained_on_subject_data','reviewed'}
    for pin in registry['pins']:
        if not isinstance(pin,dict) or not fields<=set(pin) or set(pin)-fields-{'reviewer','size_bytes'}:raise ValueError('invalid published pin')
        if 'size_bytes' in pin and (type(pin['size_bytes']) is not int or not 4<=pin['size_bytes']<=4*1024**3):raise ValueError('invalid published size')
        if 'reviewer' in pin and (not isinstance(pin['reviewer'],str) or not pin['reviewer'].strip() or len(pin['reviewer'])>512
                or any(ord(c)<32 for c in pin['reviewer'])):raise ValueError('invalid reviewer attribution')
        for field in ('id','publisher','repo','filename','revision','revision_at'):
            value=pin[field]
            if not isinstance(value,str) or not value.strip() or len(value)>512 or any(ord(c)<32 for c in value):raise ValueError('invalid pin identity')
        if (not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',pin['revision']) or not hashed(pin['artifact_sha256'])
                or pin['reviewed'] is not True or pin['artifact_kind']!='external_pretrained'
                or pin['trained_on_subject_data'] is not False):raise ValueError('unqualified published pin')
        instant(pin['revision_at'])
        if pin['id'] in pins:raise ValueError('duplicate published pin')
        pins[pin['id']]=pin
    return pins


def load_pins():
    with PIN_FILE.open('rb') as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError('pin registry too large')
    return validate_registry(json.loads(raw,object_pairs_hook=pairs))


def qualify(artifact_sha256,copy_completed_at,source='copy_time',artifact_kind='local_trained',pin_id=None):
    if not hashed(artifact_sha256) or artifact_kind not in ('external_pretrained','local_trained'):raise ValueError('invalid artifact declaration')
    copied=instant(copy_completed_at);pin=None;effective=copied
    if source=='published_artifact':
        if artifact_kind!='external_pretrained':raise ValueError('local trained artifact requires copy time')
        pin=load_pins().get(pin_id)
        if pin is None:raise ValueError('reviewed published pin missing')
        if pin['artifact_sha256']!=artifact_sha256:raise ValueError('published artifact hash mismatch')
        effective=instant(pin['revision_at'])
        if effective>copied:raise ValueError('published revision follows copy')
    elif source!='copy_time' or pin_id is not None:raise ValueError('invalid freeze source or unused pin')
    return dict(schema='encoder-freeze-v1',freeze_source=source,artifact_kind=artifact_kind,
                artifact_sha256=artifact_sha256,copy_completed_at=copied,frozen_at=effective,
                published_pin=pin,pin_sha256=hashlib.sha256(canonical(pin).encode()).hexdigest() if pin else None)


def verify(receipt,artifact_sha256,frozen_at,source):
    if not isinstance(receipt,dict):raise ValueError('qualified freeze receipt required')
    pin=receipt.get('published_pin')
    if pin is not None and not isinstance(pin,dict):raise ValueError('invalid receipt pin')
    expected=qualify(artifact_sha256,receipt.get('copy_completed_at'),source,receipt.get('artifact_kind'),pin.get('id') if pin else None)
    if canonical(expected)!=canonical(receipt) or expected['frozen_at']!=instant(frozen_at):raise ValueError('freeze receipt mismatch')
    return expected


def counts(source,total):
    if source not in SOURCES:raise ValueError('unknown freeze qualifier')
    return {s:total if s==source else 0 for s in SOURCES}
