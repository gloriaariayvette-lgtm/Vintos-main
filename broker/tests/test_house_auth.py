"""Offline admission/cutover regression tests; no server, sender or provider calls."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import house_auth as a
import house_auth_rollout as rollout
SECRET='isolated-test-house-credential-only-0000'

class Admission(unittest.TestCase):
    def test_missing_weak_and_known_default_rejected(self):
        for value in ['', 'short', ' '+SECRET]:
            with patch.dict(os.environ,{'VINTOS_SECRET':value}):
                with self.assertRaises(RuntimeError): a.require_secret()
        with patch.object(a,'LEGACY_SHA256',hashlib.sha256(SECRET.encode()).hexdigest()),patch.dict(os.environ,{'VINTOS_SECRET':SECRET}):
            with self.assertRaises(RuntimeError): a.require_secret()
        with patch.dict(os.environ,{'VINTOS_SECRET':SECRET}):self.assertEqual(a.require_secret(),SECRET)

    def test_tickets_expiry_signature_and_audience(self):
        token=a.issue(SECRET,'ws:events',60,100)
        self.assertTrue(a.valid(SECRET,token,'ws:events',101))
        for secret, audience, now in [(SECRET,'ws:telemetry',101),(SECRET,'ws:events',160),('other','ws:events',101)]:
            self.assertFalse(a.valid(secret,token,audience,now))
        for token in ['', 'x'*1600, 'bad.bad', None]:self.assertFalse(a.valid(SECRET,token,'read'))

    def call(self,path,headers=None,kind='http',protocols=None,query=b'',method='GET'):
        reached=[];messages=[]
        async def app(scope,receive,send):
            reached.append(scope.copy())
            await send({'type':'websocket.accept'} if kind=='websocket' else {'type':'http.response.start','status':200,'headers':[]})
        async def receive():return {'type':'http.request','body':b''}
        async def send(message):messages.append(message)
        scope={'type':kind,'path':path,'method':method,'headers':headers or [],'query_string':query,'subprotocols':protocols or []}
        asyncio.run(a.HouseReadGuard(app,SECRET,lambda token:token=='Bearer watch-fixture')(scope,receive,send))
        return reached,messages

    def test_every_unknown_get_and_head_denied(self):
        for path in ['/api/history','/api/memory/search','/api/new-private-route','/docs','/openapi.json','/static/private.html','/api/watch/live']:
            for method in ['GET','HEAD']:
                reached,msg=self.call(path,method=method)
                self.assertFalse(reached);self.assertEqual(msg[0]['status'],401)
                self.assertIn((b'cache-control',b'no-store'),msg[0]['headers'])

    def test_public_assets_do_not_include_memory(self):
        for path in a.PUBLIC_GETS|{'/avatar-models/public.glb','/models/public.glb'}:
            self.assertTrue(self.call(path)[0])
        self.assertFalse(a.is_public_get('/api/history'))

    def test_owner_and_cookie(self):
        reached,messages=self.call('/api/history',[(b'x-vintos-secret',SECRET.encode())]);self.assertTrue(reached)
        self.assertIn((b'cache-control',b'private, no-store'),messages[0]['headers'])
        cookie='vintos_read='+a.issue(SECRET,'read')
        self.assertTrue(self.call('/api/history',[(b'cookie',cookie.encode())])[0])
        self.assertFalse(self.call('/api/history',[(b'x-vintos-secret',b'wrong')])[0])

    def test_watch_scope_and_media(self):
        h=[(b'authorization',b'Bearer watch-fixture')]
        self.assertTrue(self.call('/api/watch/song',h)[0])
        self.assertFalse(self.call('/api/history',h)[0])
        self.assertFalse(self.call('/api/watch/live',h)[0])
        signed=a.signed_media({'url':'/api/music/stream/song.mp3'},SECRET)['url']
        path,q=signed.split('?',1)
        reached,_=self.call(path,query=q.encode());self.assertTrue(reached)
        self.assertNotIn(b'access_token',reached[0]['query_string'])
        self.assertFalse(self.call('/api/history',query=q.encode())[0])
        self.assertFalse(self.call('/api/music/stream/other.mp3',query=q.encode())[0])
        self.assertEqual(a.signed_media('https://external.invalid/api/art/x',SECRET),'https://external.invalid/api/art/x')

    def test_both_streams_reject_before_accept_and_bind_audience(self):
        for name in ['telemetry','events']:
            path='/ws/'+name
            for protocols in [[],['vintos-token.bad'],['vintos-token.'+a.issue(SECRET,'read')]]:
                reached,msg=self.call(path,kind='websocket',protocols=protocols)
                self.assertFalse(reached);self.assertEqual(msg,[{'type':'websocket.close','code':4401}])
            protocols=['vintos-v1','vintos-token.'+a.issue(SECRET,'ws:'+name)]
            reached,msg=self.call(path,kind='websocket',protocols=protocols)
            self.assertTrue(reached);self.assertEqual(msg[0]['subprotocol'],'vintos-v1')

    def test_queries_redacted_even_when_rejected(self):
        self.assertFalse(self.call('/api/history',query=b'access_token=bad')[0])

    def test_post_authorization_is_left_to_existing_handlers(self):
        self.assertTrue(self.call('/api/voice/token',method='POST')[0])

class Cutover(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='house-auth-test-')
        self.home=Path(self.tmp.name);self.assertIn('house-auth-test-',str(self.home))
        self.patch=patch.object(rollout,'home',lambda:self.home);self.patch.start()
        self.server=self.home/'Vintos/server.py';self.server.parent.mkdir();self.server.write_text('# fixture\n')
        self.calls=[]
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def runner(self,args,**kwargs):self.calls.append(args)
    def test_prepare_activate_and_protected_modes(self):
        identifier=rollout.prepare(self.server);rollout.preflight(identifier)
        self.assertFalse(rollout.env_path().exists())
        rollout.activate(identifier,self.runner)
        value=rollout.read_secret(rollout.env_path());self.assertGreaterEqual(len(value),32)
        for p in rollout.canonical_envs()+[rollout.env_path()]:
            self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertEqual(rollout.read_secret(p),value)
        self.assertEqual(self.calls,[['systemctl','--user','daemon-reload']])
        self.assertIn('house_server_guard.py',rollout.unit_paths()[0].read_text())
    def test_concurrent_configuration_aborts_without_writes(self):
        identifier=rollout.prepare(self.server)
        p=rollout.canonical_envs()[0];p.parent.mkdir(exist_ok=True);p.write_text('CHANGED=1\n')
        with self.assertRaises(ValueError):rollout.activate(identifier,self.runner)
        self.assertFalse(rollout.env_path().exists());self.assertFalse(self.calls)
    def test_activation_failure_restores_previous_configuration(self):
        p=rollout.canonical_envs()[0];p.parent.mkdir(parents=True);p.write_text('OTHER=fixture\n');p.chmod(0o640)
        identifier=rollout.prepare(self.server)
        def fail(*args,**kwargs):raise RuntimeError('stubbed systemctl failure')
        with self.assertRaises(RuntimeError):rollout.activate(identifier,fail)
        self.assertEqual(p.read_text(),'OTHER=fixture\n');self.assertEqual(p.stat().st_mode&0o777,0o640)
        self.assertFalse(rollout.env_path().exists())
    def test_guard_tamper_and_rollback_path_rejected(self):
        identifier=rollout.prepare(self.server)
        guard=rollout.state_path(identifier).parent/'guard/house_auth.py';guard.write_text('# tampered')
        with self.assertRaises(ValueError):rollout.preflight(identifier)
        with self.assertRaises(ValueError):rollout.rollback(identifier,self.runner)
        self.assertFalse(self.calls)
    def test_pi_enrollment_uses_stdin_and_environment_not_arguments(self):
        import subprocess
        tools=self.home/'tools';tools.mkdir()
        (tools/'tailscale').write_text('#!/bin/sh\nprintf "100.72.225.119\\n"\n')
        (tools/'ssh').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/ssh-args"\ncat > "$HOME/ssh-input"\n')
        for p in tools.iterdir():p.chmod(0o700)
        script=Path(__file__).resolve().parents[2]/'bin/robot-pi-repoint.sh'
        env=dict(os.environ,HOME=str(self.home),PATH=str(tools)+':/usr/bin:/bin',VINTOS_SECRET=SECRET)
        result=subprocess.run(['bash',str(script)],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        args=(self.home/'ssh-args').read_text();payload=(self.home/'ssh-input').read_text()
        self.assertNotIn(SECRET,args);self.assertNotIn(SECRET,result.stdout+result.stderr)
        self.assertEqual(payload.splitlines()[0],SECRET)
        self.assertIn("environ['VINTOS_SECRET']",payload)
        self.assertIn('EnvironmentFile=/home/pi/.config/vintos/house-auth.env',payload)
        self.assertIn("bash -s -- '100.72.225.119' '8404'",args)

    def test_finalize_binds_successful_receipt_and_rollback(self):
        identifier=rollout.prepare(self.server);rollout.activate(identifier,self.runner)
        releases=self.home/'.vintos/deploy/releases';releases.mkdir(parents=True)
        backup=self.home/'.vintos/backups/fixture';backup.mkdir(parents=True)
        (backup/'restore.sh').write_text('# fixture only\n')
        receipt={'backup':str(backup),'failures':[],'services':{'vintos-server':'active','vintos-robot-bridge':'active'},
                 'files':[{'installed_at':str(p),'sha256':rollout.digest(p)[:16]} for p in rollout.unit_paths()]}
        file=releases/'fixture.json';file.write_text(json.dumps(receipt));rollout.finalize(identifier)
        self.assertEqual(rollout.load(identifier)[1]['rollback'],str((backup/'restore.sh').resolve()))
        receipt['services']['vintos-server']='failed';file.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):rollout.finalize(identifier)
        receipt['services']['vintos-server']='active';receipt['files']=[];file.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):rollout.finalize(identifier)

    def test_secure_rollback_keeps_random_identity(self):
        identifier=rollout.prepare(self.server);rollout.activate(identifier,self.runner)
        value=rollout.read_secret(rollout.env_path());rollout.secure_rollback(identifier,self.runner)
        self.assertEqual(rollout.read_secret(rollout.env_path()),value)
        self.assertEqual(rollout.load(identifier)[1]['status'],'rolled_back_guarded')

try:
    from fastapi import FastAPI, WebSocket
    from fastapi.testclient import TestClient
    HAVE_HTTP=True
except ImportError:
    HAVE_HTTP=False

@unittest.skipUnless(HAVE_HTTP,'HTTP framework unavailable; pure ASGI tests still run')
class HTTPIntegration(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI()
        @self.app.get('/api/history')
        def private():return {'fixture':'private'}
        @self.app.websocket('/ws/{name}')
        async def stream(websocket: WebSocket,name:str):
            await websocket.accept();await websocket.send_json({'fixture':'stream'});await websocket.close()
        a.install(self.app,SECRET)
        self.client=TestClient(self.app,base_url='https://house.invalid')
    def test_session_rejects_anonymous_and_sets_secure_cookie(self):
        self.assertEqual(self.client.post('/api/auth/session').status_code,401)
        self.assertEqual(self.client.get('/api/history').status_code,401)
        response=self.client.post('/api/auth/session',headers={'X-Vintos-Secret':SECRET})
        self.assertEqual(response.status_code,200)
        self.assertIn('HttpOnly',response.headers['set-cookie']);self.assertIn('Secure',response.headers['set-cookie'])
        self.assertIn('SameSite=strict',response.headers['set-cookie'])
        self.assertNotIn(SECRET,response.text)
        self.assertEqual(self.client.get('/api/history').status_code,200)
        self.assertEqual(self.client.get('/openapi.json',headers={'Cookie':''}).status_code,401)
    def test_real_stream_handshake_for_both_audiences(self):
        from starlette.websockets import WebSocketDisconnect
        for name in ['telemetry','events']:
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('/ws/'+name):pass
            with self.client.websocket_connect('/ws/'+name,subprotocols=['vintos-v1','vintos-token.'+a.issue(SECRET,'ws:'+name)]) as ws:
                self.assertEqual(ws.accepted_subprotocol,'vintos-v1');self.assertEqual(ws.receive_json(),{'fixture':'stream'})
    def test_watch_offers_only_bounded_media_and_keeps_live_state(self):
        import types
        with tempfile.TemporaryDirectory(prefix='house-auth-watch-') as tmp,patch.dict(os.environ,{'HOME':tmp,'SPARK_WORKSPACE':tmp}):
            import watch_routes
            self.assertIn('house-auth-watch-',tmp)
            presence=watch_routes.watch_presence
            feed=types.SimpleNamespace(sent=lambda **kw:[{'url':'/api/music/stream/fixture'+str(i)+'.mp3'} for i in range(8)])
            with patch.object(presence,'authorized',lambda token:token=='Bearer watch-fixture'),patch.object(presence,'top_song',lambda:None),patch.object(presence,'record',lambda body:(True,{'stored':0})),patch.object(presence,'live_state',lambda:{'active':True}),patch.dict(sys.modules,{'landings':feed}):
                app=FastAPI();app.include_router(watch_routes.router(app_secret=SECRET))
                client=TestClient(app);headers={'Authorization':'Bearer watch-fixture'}
                response=client.get('/api/watch/landings',headers=headers)
                self.assertEqual(response.status_code,200);self.assertEqual(len(response.json()['items']),5)
                for item in response.json()['items']:
                    from urllib.parse import urlsplit,parse_qs
                    url=urlsplit(item['url']);token=parse_qs(url.query)['access_token'][0]
                    self.assertTrue(a.valid(SECRET,token,'media:'+url.path))
                self.assertEqual(client.get('/api/watch/landings').status_code,401)
                result=client.post('/api/watch/telemetry',headers=headers,json={'asleep':True})
                self.assertEqual(result.json()['live'],{'active':True})

    def test_private_guard_survives_legacy_code_and_blocks_voice(self):
        import house_server_guard
        with tempfile.TemporaryDirectory(prefix='house-auth-server-') as tmp:
            file=Path(tmp)/'server.py'
            file.write_text("from fastapi import FastAPI\napp=FastAPI()\n@app.post('/api/voice/token')\ndef voice():return {'must':'never happen anonymously'}\n")
            with patch.dict(os.environ,{'VINTOS_SECRET':SECRET}):app=house_server_guard.build(file)
            client=TestClient(app,base_url='https://house.invalid')
            self.assertEqual(client.post('/api/voice/token').status_code,401)
            self.assertEqual(client.post('/api/voice/token',headers={'X-Vintos-Secret':SECRET}).status_code,200)
            self.assertEqual(client.get('/unknown').status_code,401)

if __name__=='__main__':unittest.main()
