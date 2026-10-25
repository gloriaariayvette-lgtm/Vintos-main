"""Offline admission/cutover regression tests; no server, sender or provider calls."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import house_auth as a
SECRET='isolated-test-house-credential-only-0000'

class Admission(unittest.TestCase):
    def test_missing_weak_and_known_default_rejected(self):
        for value in ['', 'short', ' '+SECRET]:
            with patch.dict(os.environ,{'VINTOS_SECRET':value}):
                with self.assertRaises(RuntimeError): a.require_secret()
        with patch.object(a,'LEGACY_SHA256',hashlib.sha256(SECRET.encode()).hexdigest()),patch.dict(os.environ,{'VINTOS_SECRET':SECRET}):
            with self.assertRaises(RuntimeError): a.require_secret()
        with patch.dict(os.environ,{'VINTOS_SECRET':SECRET}):self.assertEqual(a.require_secret(),SECRET)
        for value in ['', 'short', ' '+SECRET]:
            with patch.dict(os.environ,{'VINTOS_SECRET':value}):self.assertEqual(a.configured_secret(log=False),'')
        self.assertFalse(a.matches('', ''));self.assertFalse(a.matches(None, SECRET));self.assertFalse(a.matches('x', ''))
        self.assertTrue(a.matches(SECRET, SECRET));self.assertFalse(a.matches(SECRET+'x', SECRET))
        with self.assertRaises(ValueError):a.issue('', 'read')
        self.assertFalse(a.valid('', a.issue(SECRET,'read'), 'read'))
        self.assertEqual(a.signed_media('/api/art/x', ''), '/api/art/x')

    def test_tickets_expiry_signature_and_audience(self):
        token=a.issue(SECRET,'ws:events',60,100)
        self.assertTrue(a.valid(SECRET,token,'ws:events',101))
        for secret, audience, now in [(SECRET,'ws:telemetry',101),(SECRET,'ws:events',160),('other','ws:events',101)]:
            self.assertFalse(a.valid(secret,token,audience,now))
        for token in ['', 'x'*1600, 'bad.bad', None]:self.assertFalse(a.valid(SECRET,token,'read'))

    def call(self,path,headers=None,kind='http',protocols=None,query=b'',method='GET',secret=SECRET,public=('/api/gcs','/api/food-order/review/{token}/approve')):
        reached=[];messages=[]
        async def app(scope,receive,send):
            reached.append(scope.copy())
            await send({'type':'websocket.accept'} if kind=='websocket' else {'type':'http.response.start','status':200,'headers':[]})
        async def receive():return {'type':'http.request','body':b''}
        async def send(message):messages.append(message)
        scope={'type':kind,'path':path,'method':method,'headers':headers or [],'query_string':query,'subprotocols':protocols or []}
        asyncio.run(a.HouseReadGuard(app,secret,lambda token:token=='Bearer watch-fixture',public_writes=public)(scope,receive,send))
        return reached,messages

    def test_every_unknown_get_and_head_denied(self):
        for path in ['/api/history','/api/memory/search','/api/new-private-route','/docs','/openapi.json','/static/private.html','/api/watch/live']:
            for method in ['GET','HEAD']:
                reached,msg=self.call(path,method=method)
                self.assertFalse(reached);self.assertEqual(msg[0]['status'],401)
                self.assertIn((b'cache-control',b'no-store'),msg[0]['headers'])

    def test_public_assets_do_not_include_memory(self):
        for path in set(a.PUBLIC_GETS)|{'/avatar-models/public.glb','/models/public.glb'}:
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

    def test_every_method_is_guarded_not_only_reads(self):
        for method in ['POST','PUT','PATCH','DELETE','OPTIONS']:
            for path in ['/api/landings','/api/stratagem/owner/stop','/api/new-private-write','/api/voice/token']:
                reached,msg=self.call(path,method=method)
                self.assertFalse(reached,(method,path));self.assertEqual(msg[0]['status'],401)
                self.assertFalse(self.call(path,[(b'x-vintos-secret',b'wrong')],method=method)[0])
                # the read session cookie is not a write credential
                self.assertFalse(self.call(path,[(b'cookie',('vintos_read='+a.issue(SECRET,'read')).encode())],method=method)[0])
            self.assertTrue(self.call('/api/landings',[(b'x-vintos-secret',SECRET.encode())],method=method)[0])

    def test_reviewed_public_writes_and_their_templates(self):
        self.assertTrue(self.call('/api/gcs',method='POST')[0])
        self.assertTrue(self.call('/api/food-order/review/abc/approve',method='POST')[0])
        self.assertFalse(self.call('/api/food-order/review/abc/def/approve',method='POST')[0])
        self.assertFalse(self.call('/api/gcs/other',method='POST')[0])
        self.assertTrue(self.call('/api/auth/session',method='POST')[0])   # it checks the credential itself

    def test_watch_bearer_on_watch_writes_only(self):
        h=[(b'authorization',b'Bearer watch-fixture')]
        for path in ['/api/watch/telemetry','/api/watch/register','/api/voice/token']:
            self.assertFalse(self.call(path,method='POST')[0]);self.assertTrue(self.call(path,h,method='POST')[0])
        self.assertFalse(self.call('/api/watch/live',h,method='POST')[0])
        self.assertFalse(self.call('/api/landings',h,method='POST')[0])

    def test_cookie_admits_only_the_plain_forms_and_stage_query_only_its_pages(self):
        cookie=[(b'cookie',('vintos_read='+a.issue(SECRET,'read')).encode())]
        self.assertTrue(self.call('/aq/answer',cookie,method='POST')[0])
        self.assertFalse(self.call('/aq/answer',method='POST')[0])
        self.assertTrue(self.call('/avatar/stage/stills',query=('s='+SECRET).encode())[0])
        self.assertFalse(self.call('/avatar/stage/stills',query=b's=wrong')[0])
        self.assertFalse(self.call('/api/history',query=('s='+SECRET).encode())[0])

    def test_unconfigured_fails_closed_but_public_still_answers(self):
        for method in ['GET','POST']:
            for headers in [[],[(b'x-vintos-secret',b'')],[(b'x-vintos-secret',SECRET.encode())]]:
                reached,msg=self.call('/api/history',headers,method=method,secret='')
                self.assertFalse(reached);self.assertEqual(msg[0]['status'],503)
        self.assertTrue(self.call('/',secret='')[0]);self.assertTrue(self.call('/api/gcs',method='POST',secret='')[0])
        for name in ['telemetry','events']:
            reached,msg=self.call('/ws/'+name,[(b'x-vintos-secret',b'')],kind='websocket',secret='')
            self.assertFalse(reached);self.assertEqual(msg,[{'type':'websocket.close','code':4401}])

    def test_unknown_websocket_needs_the_credential(self):
        reached,msg=self.call('/ws/other',kind='websocket',protocols=['vintos-token.'+a.issue(SECRET,'ws:other')])
        self.assertFalse(reached);self.assertEqual(msg,[{'type':'websocket.close','code':4401}])
        self.assertTrue(self.call('/ws/other',[(b'x-vintos-secret',SECRET.encode())],kind='websocket')[0])

    def test_pushed_links_open_exactly_their_own_path(self):
        url=a.link('http://100.72.225.119:8500/api/video/file/clip.mp4',secret=SECRET)
        path,q=url.split('8500',1)[1].split('?',1)
        self.assertTrue(self.call(path,query=q.encode())[0])
        self.assertFalse(self.call('/api/video/file/other.mp4',query=q.encode())[0])
        self.assertFalse(self.call('/api/chat/history',query=q.encode())[0])
        self.assertFalse(self.call(path,query=q.encode(),method='POST')[0])
        token=dict(__import__('urllib.parse').parse.parse_qsl(q))['access_token']
        self.assertTrue(a.valid(SECRET,token,'link:'+path,time.time()+6*86400))
        self.assertFalse(a.valid(SECRET,token,'link:'+path,time.time()+8*86400))
        self.assertFalse(a.valid(SECRET,a.issue(SECRET,'read',7*86400),'read',time.time()+7200))   # sessions stay short
        aq=a.link('https://aegis.tailaa3de5.ts.net:8443/aq?qid=q1',secret=SECRET).split('8443',1)[1]
        self.assertTrue(self.call('/aq',query=aq.split('?',1)[1].encode())[0])
        answer='access_token='+a.issue(SECRET,'link:/aq/answer',3600)
        self.assertTrue(self.call('/aq/answer',query=answer.encode(),method='POST')[0])
        self.assertFalse(self.call('/aq/answer',query=aq.split('?',1)[1].encode(),method='POST')[0])
        for other in ['https://external.invalid/api/art/x','http://100.72.225.119:8500/api/chat/history']:
            self.assertEqual(a.link(other,secret=SECRET),other)
        self.assertEqual(a.link('http://100.72.225.119:8500/api/art/x',secret=''),'http://100.72.225.119:8500/api/art/x') if not os.environ.get('VINTOS_SECRET') else None

    def test_capability_pages_are_exactly_one_item(self):
        self.assertTrue(self.call('/api/gloria/asks/q1')[0]);self.assertFalse(self.call('/api/gloria/asks')[0])
        self.assertFalse(self.call('/api/gloria/asks/q1/extra')[0])
        self.assertTrue(self.call('/api/food-order/review/tok')[0]);self.assertFalse(self.call('/api/food-order/review/tok/x')[0])

    def test_both_copies_are_identical(self):
        root=Path(__file__).resolve().parents[2]
        self.assertEqual((root/'bin/house_auth.py').read_bytes(),(root/'scripts/house_auth.py').read_bytes())

class PiEnrollment(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='house-auth-test-')
        self.home=Path(self.tmp.name);self.assertIn('house-auth-test-',str(self.home))
    def tearDown(self):self.tmp.cleanup()
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

if __name__=='__main__':unittest.main()
