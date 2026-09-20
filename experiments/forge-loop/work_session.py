"""Bounded local orchestration contract for temporarily borrowing Gemma from the Lab.

Lab adapter must cooperatively checkpoint, await quiescence, and enforce pause-owner
identity. No service names, shell commands or live endpoints are guessed here.
A persistent restore obligation is recorded BEFORE pausing; restart recovery is explicit.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import secrets
import time
from taskmarket import screen


class WorkSession:
    def __init__(self, state_file, lab, notify, *, cancel_url, cancel_token):
        self.path = Path(state_file).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lab, self.notify = lab, notify
        self.cancel_url, self.cancel_token = cancel_url, cancel_token

    @contextmanager
    def lock(self):
        with open(str(self.path)+'.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def save(self, state):
        temporary=self.path.with_suffix('.tmp')
        with open(temporary,'w') as f:
            json.dump(state,f);f.flush();os.fsync(f.fileno())
        os.replace(temporary,self.path);self.path.chmod(0o600)

    def event(self, state, kind, detail=None, high=False):
        # Durable before delivery, including resume failures. No task/private input content.
        event={'id':secrets.token_hex(12),'kind':kind,'detail':detail,'sent':False,'priority':4 if high else 3}
        state.setdefault('events',[]).append(event);self.save(state)
        self.flush(state)

    def flush(self, state):
        for event in state.get('events',[]):
            if event['sent']:continue
            payload={'title':'Forge work: '+event['kind'],'message':event['detail'] or event['kind'],
                     'priority':event['priority'],'actions':[{'action':'http','label':'Cancel',
                     'url':self.cancel_url,'method':'POST','headers':{'Authorization':'Bearer '+self.cancel_token},'clear':True}]}
            try:event['sent']=self.notify(payload) is True
            except Exception:event['sent']=False
            self.save(state)

    def restore(self, state):
        if not state.get('restore_due'):return
        # Adapter MUST be idempotent, restore only this owner's pause, and preserve
        # an independent manual OFF. receipt contains observed state, not an assumption.
        receipt=self.lab.restore(state['id'],state['before'])
        if receipt.get('restored') is not True:
            raise RuntimeError('Lab restoration unconfirmed')
        state.update(restore_due=False,phase='restored',restore_receipt=receipt)
        self.event(state,'lab_restored')

    def recover(self):
        with self.lock():
            state=json.loads(self.path.read_text())
            self.restore(state);self.flush(state)
            return state

    def run(self, discover, assess, inventory, perform_local, cancelled, *, max_tasks=3, seconds=1800):
        if type(max_tasks) is not int or not 1 <= max_tasks <= 3 or type(seconds) is not int or not 1 <= seconds <= 1800:
            raise ValueError('pilot limited to 1–3 tasks and at most 30 minutes')
        with self.lock():
            if self.path.exists():
                previous=json.loads(self.path.read_text())
                if previous.get('restore_due'):
                    raise RuntimeError('restore the previous Lab session before starting another')
                if any(not e['sent'] for e in previous.get('events',[])):
                    raise RuntimeError('retry pending notifications before starting another session')
                archive=self.path.parent/'sessions';archive.mkdir(exist_ok=True,mode=0o700)
                record=archive/(previous['id']+'.json')
                if not record.exists():
                    with record.open('x') as output:
                        json.dump(previous,output);output.flush();os.fsync(output.fileno())
                    record.chmod(0o600)
            state={'id':secrets.token_hex(16),'before':self.lab.status(),'phase':'pausing',
                   'restore_due':True,'events':[],'results':[],'deadline':time.time()+seconds}
            self.save(state)
            try:
                paused=self.lab.pause(state['id'])
                if paused.get('owner') != state['id'] or paused.get('quiescent') is not True:
                    raise RuntimeError('Lab pause/checkpoint not confirmed; work refused')
                state['phase']='working';self.event(state,'lab_paused')
                for task in discover():
                    if cancelled() or time.time() >= state['deadline'] or len(state['results']) >= max_tasks:break
                    admission=screen(task,assess(task),inventory)
                    if not admission['eligible_local_trial']:continue
                    if cancelled() or time.time() >= state['deadline']:break
                    # Trusted local runner must enforce this absolute deadline and cancellation.
                    result=perform_local(task,deadline=state['deadline'],cancelled=cancelled)
                    state['results'].append({'task_id':task['id'],'result':result})
                    self.event(state,'local_work_finished','Local artifact produced; not submitted or paid.')
                self.event(state,'session_cancelled' if cancelled() else 'session_finished')
            except BaseException:
                self.event(state,'session_failed','Work stopped; restoring Lab.',high=True)
                raise
            finally:
                try:self.restore(state)
                except BaseException:
                    state['phase']='restore_required'
                    self.event(state,'lab_restore_failed','Lab restoration needs recovery.',high=True)
                    raise
            return state
