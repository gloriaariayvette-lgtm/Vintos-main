"""Three real sandboxed Forge cycles, with fixture models, in a throwaway Atelier."""
from pathlib import Path
import json
import tempfile
from controller import Controller
from adapters import ForgeSandboxBuilder, publish_pending


def main():
    owner, worker = 'fixture-owner-'+'a'*40, 'fixture-worker-'+'b'*40
    calls = []
    def astra(*args, **kwargs):
        number=len(calls)+1;calls.append(number)
        return json.dumps({'module':f'def skill(note):\n    return note.upper() + " revision {number}"\n',
                           'test':f'from skill import skill\nassert skill("test") == "TEST revision {number}"\nprint("1/1")\n'})
    builder=ForgeSandboxBuilder(astra,lambda *a,**k:'PASS',
                                lambda code,ctx:{'complete':ctx['cycles']==2,'reason':'fixture acceptance target'})
    with tempfile.TemporaryDirectory(prefix='forge-atelier-local-') as directory:
        controller=Controller(Path(directory)/'atelier/loop.sqlite',owner,worker,'https://fixture.invalid')
        project=controller.create(owner,'Fixture: refine a string transformer',['skill'])
        state=controller.drive(worker,project['id'],lambda ctx:{'capability':'skill'},builder)
        messages=[]
        publish_pending(controller,owner,project['id'],project['cancel_token'],'fixture',lambda m:messages.append(m) or True)
        artifacts=controller.end_private(owner,project['id'],'audit')
        assert state=='complete' and len(artifacts)==3 and len(messages)==3
        print(json.dumps({'fixture_models':True,'live_calls':0,'paid_calls':0,'host_writes':0,
                          'state':state,'accepted_artifacts':len(artifacts),'sandbox_checks':len(calls),
                          'ntfy_payloads_built_not_sent':len(messages),'wallet':'unconnected'},indent=2))

if __name__=='__main__':main()
