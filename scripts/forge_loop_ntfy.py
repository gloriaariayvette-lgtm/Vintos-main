"""Explicit ntfy transport; never discovers a topic, token or household config."""
import json
from urllib.parse import urlsplit
from urllib.request import Request
from lab_http import open_request


class NtfyPublisher:
    def __init__(self, server, topic, token, *, transport=None):
        parsed=urlsplit(server)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('explicit HTTPS ntfy server required')
        if not topic or '/' in topic or any(c in topic for c in '\r\n'):
            raise ValueError('single explicit topic required')
        if not token or any(c in token for c in '\r\n'):
            raise ValueError('explicit ntfy authorization required')
        self.server,self.topic,self.token,self.transport=server.rstrip('/'),topic,token,transport or open_request

    def __call__(self, payload):
        body=dict(payload,topic=self.topic)
        request=Request(self.server+'/',data=json.dumps(body).encode(),method='POST',
                        headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.transport(request,timeout=10) as response:
            if not 200 <= response.status < 300:return False
            receipt=json.loads(response.read(65536))
            return receipt.get('event')=='message' and receipt.get('topic')==self.topic and bool(receipt.get('id'))
