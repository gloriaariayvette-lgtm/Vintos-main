"""Durable per-work diagnostic collection and generation-scoped delivery."""
from contextlib import contextmanager
from pathlib import Path
import copy,fcntl,hashlib,json,math,os,re,tempfile,uuid
DAY=86400
ACTIVE=('awaiting_evidence','evidence_changed','actionable')
class LedgerUnavailable(RuntimeError): pass
class DiagnosticReceipt:
    def __init__(self,wid,targets,hashes,generation):
        self.work_id=wid;self.targets=targets;self.hashes=hashes;self.generation=generation
class Store:
    def __init__(self,path=None,workspace=None):
        self.workspace=Path(workspace or os.environ.get('SPARK_WORKSPACE',os.path.expanduser('~/.vintos/workspace')))
        self.path=Path(path) if path else self.workspace/'memory/dot-channel/awaiting-evidence.json'
    def _load(self):
        try:
            d=json.loads(self.path.read_text()) if self.path.exists() else {'version':1,'items':{}}
            if not isinstance(d,dict) or d.get('version')!=1 or not isinstance(d.get('items'),dict):raise ValueError('schema')
            required={'work','targets','status','baseline','current','generation','sent_generation','next_due','next_send','paused_until','history'}
            for v in d['items'].values():
                if not isinstance(v,dict) or not required.issubset(v):raise ValueError('item schema')
                if not isinstance(v['work'],dict) or not isinstance(v['targets'],list) or not isinstance(v['history'],list):raise ValueError('item schema')
                if any(type(v[k]) not in (int,float) or not math.isfinite(v[k]) for k in ('generation','sent_generation','next_due','next_send','paused_until')):raise ValueError('item numeric schema')
            if not isinstance(d.get('owner_requests',{}),dict) or any(not isinstance(v,dict) for v in d.get('owner_requests',{}).values()):raise ValueError('owner request schema')
            for v in d.get('owner_requests',{}).values():
                if not {'id','kind','scope','destination','expires','token'}.issubset(v) or not isinstance(v['scope'],list) or not isinstance(v['destination'],list):raise ValueError('owner request schema')
                if type(v['expires']) not in (int,float) or not math.isfinite(v['expires']):raise ValueError('owner expiry schema')
            return d
        except (OSError,ValueError,TypeError) as exc:raise LedgerUnavailable('evidence ledger unavailable') from exc
    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with open(str(self.path)+'.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);d=self._load();yield d
            fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix='.evidence-')
            try:
                with os.fdopen(fd,'w') as f:json.dump(d,f,sort_keys=True);f.flush();os.fsync(f.fileno())
                os.replace(tmp,self.path)
                fd=os.open(self.path.parent,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
    def read(self):return self._load()['items']
    def safe_read(self):
        try:return self.read()
        except (LedgerUnavailable,OSError):return {}
    def active(self):return {k:v for k,v in self.safe_read().items() if v.get('status') in ACTIVE}
    def _targets(self,work):
        m=re.search(r'\bModelJSONError\s+([0-9a-f]{32})\b',work.get('goal',''))
        if not m:return []
        base=self.workspace/'memory/chemistry-lab/diagnostics'
        return [str(base/(m[1]+s)) for s in ('.raw.txt','.events.json')]
    def _observations(self,targets):
        out={}
        for name in targets:
            p=Path(name)
            if p.is_symlink() or any(x.is_symlink() for x in p.parents):continue
            try:
                with p.open('rb') as f:b=f.read(65537)
            except OSError:continue
            if not b or len(b)>65536:continue
            if p.name.endswith('.events.json'):
                try:e=json.loads(b)
                except ValueError:continue
                if not isinstance(e,dict) or e.get('evidence_id')!=p.name.split('.')[0]:continue
            out[name]=hashlib.sha256(b).hexdigest()
        return out
    def _observe(self,item,now):
        current=self._observations(item['targets'])
        prior=item.get('current',item.get('baseline',{}))
        changed=current!=prior
        item['last_checked_at']=float(now)
        if changed:
            item['generation']+=1
            item['history'].append({'kind':'bytes_changed','at':float(now),'generation':item['generation'],'previous':prior,'current':current})
            item.update(current=current,status='evidence_changed',evidence_at=float(now))
        # Every committed observation can precede a crash before accept(),
        # including the due daily collector. Keep complete evidence replayable.
        item['pending_receipt']=len(current)==2 and item['status']=='evidence_changed'
        return current,changed
    def enter(self,work,reason,now):
        wid=work['id']
        if not re.fullmatch(r'RW-[0-9a-f]{8}',wid):raise ValueError('stable work ID required')
        with self.transaction() as d:
            if wid in d['items']:
                item=d['items'][wid]
                if item['status']=='actionable':
                    current,_=self._observe(item,now)
                    if len(current)!=2:
                        item.update(status='awaiting_evidence',reason=str(reason)[:600])
                        item.pop('next_action',None);item.pop('relevant_hashes',None)
                        item['history'].append({'kind':'reentered_wait','at':float(now),'generation':item['generation']})
                    else:item['status']='actionable'
                return copy.deepcopy(item)
            targets=self._targets(work)
            if not targets:raise ValueError('unsupported collector')
            current=self._observations(targets)
            item={'work':copy.deepcopy(work),'reason':str(reason)[:600],'targets':targets,'baseline':current,'current':current,
                  'status':'awaiting_evidence','entered_at':float(now),'generation':0,'sent_generation':-1,
                  'next_due':float(now)+DAY,'next_send':float(now),'paused_until':float(work.get('paused_until') or 0),
                  'history':[],'last_checked_at':float(now),'initial_statement':True}
            # Entry is an actual bounded local check. Existing complete files
            # disprove the missing-files premise and enable their inspection.
            if len(current)==2:
                item.update(status='actionable',next_action='inspect_saved_diagnostic',evidence_at=float(now),relevant_hashes=current)
                item['history'].append({'kind':'complete_current_set_at_entry','at':float(now),'generation':0,'hashes':current})
            d['items'][wid]=item;return copy.deepcopy(item)
    def collect(self,wid,now):
        """Production adapter: reserve local check before reading; no external IO."""
        with self.transaction() as d:
            item=d['items'].get(wid)
            if not item or item['status'] not in ACTIVE or item['status']=='actionable' or now<item['paused_until'] or now<item['next_due']:return None
            item['next_due']=float(now)+DAY
            current,changed=self._observe(item,now)
            item['history'].append({'kind':'local_check','at':float(now),'generation':item['generation'],'hashes':current})
            return DiagnosticReceipt(wid,list(item['targets']),current,item['generation'])
    def ingest_arrival(self,wid,now):
        """Bounded local arrival ingestion, independent of discovery/send clocks.
        Called by the host's local tick, including while posting is paused.
        Only changed bytes produce a receipt; no network or rerun is enabled.
        """
        with self.transaction() as d:
            item=d['items'].get(wid)
            if not item or item['status'] not in ('awaiting_evidence','evidence_changed'):return None
            current,changed=self._observe(item,now)
            if not changed and not item.get('pending_receipt'):return None
            item['history'].append({'kind':'local_artifact_arrival','at':float(now),'generation':item['generation'],'hashes':current})
            return DiagnosticReceipt(wid,list(item['targets']),current,item['generation'])
    def accept(self,receipt,now):
        if not isinstance(receipt,DiagnosticReceipt):return False
        with self.transaction() as d:
            item=d['items'].get(receipt.work_id)
            if not item or item['status'] not in ACTIVE:return False
            if receipt.targets!=item['targets'] or receipt.generation!=item['generation']:return False
            current=self._observations(item['targets'])
            if len(current)!=2 or current!=receipt.hashes or current!=item['current']:return False
            # Complete CURRENT set, not only hashes changed in the last tick.
            # Raw-first and events-first arrivals are equally valid.
            item.update(status='actionable',next_action='inspect_saved_diagnostic',evidence_at=float(now),relevant_hashes=current)
            item.pop('pending_receipt',None)
            item['history'].append({'kind':'relevant_local_inspection_enabled','at':float(now),'generation':item['generation'],'hashes':current,'baseline':item['baseline']})
            return True
    def pause(self,wid,until):
        with self.transaction() as d:
            if wid in d['items']:d['items'][wid]['paused_until']=max(d['items'][wid]['paused_until'],float(until))
    def finish(self,wid,state,now):
        with self.transaction() as d:
            item=d['items'].get(wid)
            if not item:return 'untracked'
            if item['status'] in ('resolved','cancelled'):return 'durable'
            if item['status']!='actionable':return 'tracked-closure-failed'
            item.update(status='resolved',resolution=state,resolved_at=float(now))
            return 'durable' 
    def register_owner(self,request):
        with self.transaction() as d:
            rows=d.setdefault('owner_requests',{})
            if request['id'] not in rows:rows[request['id']]=dict(request,token=uuid.uuid4().hex)
            return copy.deepcopy(rows[request['id']])
    @staticmethod
    def _owner(d,request,kind,now,destination=None):
        actual=d.get('owner_requests',{}).get((request or {}).get('id'))
        if not actual or actual!=request or actual.get('kind')!=kind or actual.get('used') or now>=actual['expires']:return None
        if destination is not None and list(destination)!=actual['destination']:return None
        return actual
    def owner(self,request,kind,now,destination=None):
        # Cancellation remains an explicitly authenticated owner operation.
        if kind!='cancel':return False
        with self.transaction() as d:
            actual=self._owner(d,request,kind,now,destination)
            if not actual:return False
            item=d['items'].get(actual['scope'][0])
            if not item or item['status'] not in ACTIVE:return False
            item.update(status='cancelled',cancelled_at=float(now),cancelled_by=actual['id'])
            item['history'].append({'kind':'cancel','at':float(now),'owner_request':actual['id'],'generation':item['generation']})
            actual['used']=True;return True
    def statements(self,wids,now,owner=None,destination=None):
        """The sole delivery reservation: generation + rolling day, before send.
        Unknown transport outcome consumes it. Owner replies use this same path.
        """
        result={}
        with self.transaction() as d:
            actual=self._owner(d,owner,'status',now,destination)
            used_owner=False
            for wid in dict.fromkeys(wids):
                item=d['items'].get(wid)
                if not item or item['status'] not in ACTIVE:
                    result[wid]=None;continue
                if now<item['paused_until']:continue
                if item['status']=='actionable':
                    result[wid]=None;continue
                direct=actual and wid in actual['scope']
                if not direct and item['generation']<=item['sent_generation'] and now<item['next_send']:continue
                item['sent_generation']=item['generation'];item['next_send']=float(now)+DAY
                item['history'].append({'kind':'send_reserved','at':float(now),'generation':item['generation'],'owner_request':actual['id'] if direct else None})
                result[wid]=self.status_text(wid,item);item['initial_statement']=False
                used_owner=used_owner or bool(direct)
            if used_owner:actual['used']=True
        return result
    def statement(self,wid,now):return self.statements([wid],now).get(wid)
    @staticmethod
    def status_text(wid,item):
        if item['status']=='actionable':return wid+': saved local diagnostic files are ready for the already-authorized local inspection; no rerun or outreach is enabled.'
        if item.get('initial_statement'):return wid+': set aside pending local diagnostic evidence; ownership retained.'
        if item['status']=='evidence_changed':return wid+': tracked local diagnostic bytes changed; the complete relevant pair is not yet available.'
        return wid+': awaiting evidence; ownership retained. No change in the tracked local diagnostic files.'
def store():return Store()
