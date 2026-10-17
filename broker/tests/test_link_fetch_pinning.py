#!/usr/bin/env python3
"""Offline transport regressions: real urllib3 HTTP/TLS, only fake or AF_UNIX sockets.
The PEM key is a public test fixture, never a deployment credential.
"""
import gzip
import io
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import link_fetch as L

PUBLIC = '93.184.216.34'
V6 = '2606:4700:4700::1111'
FIXTURES = Path(__file__).parent / 'fixtures'


def response(body=b'public page', status=200, headers=()):
    return (('HTTP/1.1 %d OK\r\nContent-Length: %d\r\nConnection: close\r\n' % (status, len(body))).encode()
            + b''.join(('%s: %s\r\n' % pair).encode() for pair in headers) + b'\r\n' + body)


class Wire:
    def __init__(self, raw, contacts, sent, family, fail=None):
        self.raw, self.contacts, self.sent, self.family, self.fail = raw, contacts, sent, family, fail
        self.closed = False
    def settimeout(self, value): self.timeout = value
    def setsockopt(self, *args): pass
    def connect(self, address):
        self.contacts.append((self.family, address))
        # Numeric public destinations are mandatory even in the offline fixture.
        assert L.refusal('http://[%s]/' % address[0] if ':' in address[0] else 'http://%s/' % address[0]) == ''
        if self.fail: raise self.fail
    def sendall(self, data): self.sent.append(bytes(data))
    def makefile(self, *args, **kwargs): return io.BytesIO(self.raw)
    def close(self): self.closed = True
    def shutdown(self, *args): pass


class PinnedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='link-pinning-')
        self.addCleanup(self.tmp.cleanup)
        self.contacts, self.sent, self.wires, self.answers, self.dns = [], [], [], [], []
        self.env = patch.dict(os.environ, {'HOME': self.tmp.name, 'HTTP_PROXY': 'http://127.0.0.1:9',
                             'HTTPS_PROXY': 'http://127.0.0.1:9', 'ALL_PROXY': 'socks5h://127.0.0.1:9',
                             'REQUESTS_CA_BUNDLE': '', 'CURL_CA_BUNDLE': ''})
        self.env.start(); self.addCleanup(self.env.stop)
        self.sockets = patch.object(socket, 'socket', side_effect=self.socket)
        self.sockets.start(); self.addCleanup(self.sockets.stop)
        self.resolver = patch.object(socket, 'getaddrinfo', side_effect=self.resolve)
        self.resolver.start(); self.addCleanup(self.resolver.stop)
        self.create = patch.object(socket, 'create_connection', side_effect=AssertionError('unbound connection'))
        self.create.start(); self.addCleanup(self.create.stop)
        self.assertTrue(os.environ['HOME'].startswith('/'))
        self.assertIsNot(socket.socket, self.socket)
    def resolve(self, host, *args, **kwargs):
        self.dns.append(host)
        # A second lookup yields loopback: old requests transport would contact it.
        address = PUBLIC if len(self.dns) == 1 else '127.0.0.1'
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (address, 0))]
    def socket(self, family, *args, **kwargs):
        raw, fail = self.answers.pop(0) if self.answers else (response(), None)
        wire = Wire(raw, self.contacts, self.sent, family, fail)
        self.wires.append(wire)
        return wire
    def fetch(self, url='http://reader.example/a', **kw):
        return L.fetch(url, article_route=False, **kw)
    def test_public_to_private_rebinding_never_connects_private(self):
        r = self.fetch()
        self.assertTrue(r['fetched'], r)
        self.assertEqual(self.dns, ['reader.example'])
        self.assertEqual(self.contacts, [(socket.AF_INET, (PUBLIC, 80))])
        self.assertIn(b'Host: reader.example\r\n', b''.join(self.sent))
        self.assertNotIn(b'Authorization', b''.join(self.sent))
    def test_retry_ipv6_to_ipv4_uses_only_snapshot(self):
        self.answers = [(b'', OSError('IPv6 unavailable')), (response(), None)]
        r = self.fetch(resolve=lambda h: [V6, PUBLIC, PUBLIC])
        self.assertTrue(r['fetched'], r)
        self.assertEqual(self.contacts, [(socket.AF_INET6, (V6, 80, 0, 0)), (socket.AF_INET, (PUBLIC, 80))])
        self.assertTrue(self.wires[0].closed)
        self.assertEqual(self.dns, [])
    def test_failure_exhausts_snapshot_without_resolving_again(self):
        self.answers = [(b'', socket.timeout('timed out'))] * 2
        r = self.fetch(resolve=lambda h: [PUBLIC, V6])
        self.assertEqual(r['kind'], 'http_failure')
        self.assertIn('timed out', r['why'])
        self.assertEqual(len(self.contacts), 2)
        self.assertTrue(all(w.closed for w in self.wires))
        self.assertEqual(self.dns, [])
    def test_dns_failure_empty_mixed_invalid_and_scoped_refused(self):
        for addresses in ([], [PUBLIC, '10.0.0.1'], [PUBLIC, '::1'], ['invalid'], [V6 + '%eth0']):
            r = self.fetch(resolve=lambda h: addresses)
            self.assertEqual(r['kind'], 'refused', r)
        def bad(h): raise socket.gaierror('DNS unavailable')
        self.assertIn('DNS unavailable', self.fetch(resolve=bad)['why'])
        self.assertEqual(self.contacts, [])
    def test_literal_ipv4_ipv6_do_not_resolve(self):
        for url in ('http://%s/' % PUBLIC, 'http://[%s]/' % V6):
            self.assertTrue(self.fetch(url)['fetched'])
        self.assertEqual(self.dns, [])
    def test_redirect_rechecks_dns_even_same_host(self):
        self.answers = [(response(status=302, headers=[('Location', '/next')]), None)]
        r = self.fetch()
        self.assertEqual(r['kind'], 'refused', r)
        self.assertEqual(len(self.contacts), 1)
        self.assertEqual(self.dns, ['reader.example', 'reader.example'])
    def test_meta_refresh_rechecks_dns(self):
        self.answers = [(response(b'<html><meta http-equiv="refresh" content="0;url=/next"></html>',
                                 headers=[('Content-Type', 'text/html')]), None)]
        self.assertEqual(self.fetch()['kind'], 'refused')
        self.assertEqual(len(self.contacts), 1)
        self.assertEqual(len(self.dns), 2)
    def test_new_redirect_public_snapshot_is_pinned(self):
        self.answers = [(response(status=302, headers=[('Location', 'http://next.example/b')]), None)]
        lookups = []
        def dns(host):
            lookups.append(host)
            return [PUBLIC] if host == 'reader.example' else [V6]
        self.assertTrue(self.fetch(resolve=dns)['fetched'])
        self.assertEqual(lookups, ['reader.example', 'next.example'])
        self.assertEqual(self.contacts[-1], (socket.AF_INET6, (V6, 80, 0, 0)))
        self.assertEqual(self.dns, [])
    def test_gzip_cap_and_timeouts_preserved(self):
        self.answers = [(response(gzip.compress(b'x' * 4000), headers=[('Content-Encoding', 'gzip')]), None)]
        r = self.fetch(max_bytes=100, timeout=3)
        self.assertEqual(r['kind'], 'truncated', r)
        self.assertEqual(r['bytes'], 100)
        self.assertEqual(self.wires[0].timeout, 3)
        self.assertTrue(self.wires[0].closed)
    def test_http_failure_status_preserved(self):
        self.answers = [(response(status=503), None)]
        self.assertEqual(self.fetch()['http_status'], 503)
    def test_europepmc_and_x_alternates_use_pinning(self):
        import urllib3
        # A plain pool here exercises all production DNS/connection code without TLS.
        # Real TLS identity/verification is exercised separately below.
        from urllib3.connection import HTTPConnection, HTTPSConnection
        with patch.object(HTTPSConnection, 'connect', HTTPConnection.connect):
            self.answers = [(response(status=302, headers=[('Location', 'http://private.example/')]), None)]
            r = L.fetch('https://pmc.ncbi.nlm.nih.gov/articles/PMC10742211/')
        self.assertFalse(r['fetched'])
        self.assertEqual(r['europepmc']['kind'], 'refused')
        self.assertEqual(self.dns, ['www.ebi.ac.uk', 'private.example', 'pmc.ncbi.nlm.nih.gov'])
        self.assertEqual(len(self.contacts), 1)
        self.dns.clear(); self.contacts.clear()
        with patch.object(HTTPSConnection, 'connect', HTTPConnection.connect):
            self.answers = [(response(b'{"html":"<p>post</p>"}', headers=[('Content-Type', 'application/json')]), None)]
            r = L.fetch('https://x.com/reader/status/1234567')
        self.assertTrue(r['fetched'], r)
        self.assertEqual(self.dns, ['publish.twitter.com'])
        self.assertEqual(self.contacts, [(socket.AF_INET, (PUBLIC, 443))])
    def tls(self, host, trust):
        # Real TLS over AF_UNIX socketpair: zero IP traffic, including loopback.
        self.sockets.stop()
        try: client, server = socket.socketpair()
        finally: self.sockets.start()
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(FIXTURES / 'link_fetch_tls_cert.pem'), str(FIXTURES / 'link_fetch_tls_key.pem'))
        names, errors, request = [], [], []
        server_context.set_servername_callback(lambda sock, name, ctx: names.append(name))
        def serve():
            try:
                with server_context.wrap_socket(server, server_side=True) as peer:
                    data = peer.recv(65536)
                    if data:
                        request.append(data)
                        peer.sendall(response())
            except (ssl.SSLError, OSError) as exc: errors.append(str(exc))
            finally: server.close()
        server.settimeout(3)
        thread = threading.Thread(target=serve, daemon=True); thread.start()
        class Pair:
            def setsockopt(self, *args): pass  # AF_UNIX has no TCP_NODELAY
            def __getattr__(self, name): return getattr(client, name)
            def connect(pair, address): self.contacts.append((socket.AF_INET, address))
        try:
            with patch.object(socket, 'socket', return_value=Pair()):
                with patch.dict(os.environ, {'REQUESTS_CA_BUNDLE': str(FIXTURES / 'link_fetch_tls_cert.pem') if trust else ''}):
                    r = self.fetch('https://%s/' % host, resolve=lambda h: [PUBLIC], timeout=3)
        finally:
            client.close(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(names, [host], (r, errors))
        self.assertEqual(self.contacts, [(socket.AF_INET, (PUBLIC, 443))])
        self.assertEqual(self.dns, [])
        return r, request
    def test_https_uses_hostname_for_sni_host_and_cert_verification(self):
        r, request = self.tls('reader.example', True)
        self.assertTrue(r['fetched'], r)
        self.assertIn(b'Host: reader.example\r\n', request[0])
    def test_https_wrong_hostname_fails(self):
        r, request = self.tls('wrong.example', True)
        self.assertEqual(r['kind'], 'http_failure', r)
        self.assertRegex(r['why'].lower(), 'hostname|match')
        self.assertEqual(request, [])
    def test_https_untrusted_certificate_fails(self):
        r, request = self.tls('reader.example', False)
        self.assertEqual(r['kind'], 'http_failure', r)
        self.assertIn('CERTIFICATE_VERIFY_FAILED', r['why'])
        self.assertEqual(request, [])


if __name__ == '__main__': unittest.main()
