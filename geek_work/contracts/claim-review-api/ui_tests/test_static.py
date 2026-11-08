"""Static routing does not weaken the POST API authorization boundary."""
import http.client
import sys
from pathlib import Path
import unittest
BRAIN=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BRAIN/'contracts/claim-review-api/server_tests'))
from test_server import ServerTests


class StaticTests(ServerTests):
    # Reuse setup/cleanup only; do not recount the inherited server test suite.
    def get(self,path,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        c.request('GET',path,headers=headers or {})
        r=c.getresponse();result=r.status,dict(r.getheaders()),r.read();c.close();return result

    def test_static_allowlist(self):
        for path in ('/','/ui/app.js','/ui/core.js','/ui/style.css'):
            status,headers,raw=self.get(path)
            self.assertEqual(status,200)
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
            self.assertNotIn(self.c.token.encode(),raw)
            self.assertNotIn(self.c.id.encode(),raw)

    def test_static_denies_paths_and_query(self):
        for path in ('/session-token','/session.json','/ui/../tools/geek_work_claim_api_server.py','/?token=example','/v1/context'):
            self.assertEqual(self.get(path)[0],404)

    def test_static_rejects_foreign_host_origin(self):
        for headers in ({'Host':'localhost:'+str(self.server.server_address[1])},{'Origin':'null'},{'Origin':'https://example.invalid'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.get('/',headers)[0],403)

    def test_static_does_not_authorize_api(self):
        self.assertEqual(self.get('/')[0],200)
        self.h.send('missing_auth',self.h.request('context'),401,'unauthorized',headers={'Authorization':None})


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(StaticTests(name) for name in StaticTests.__dict__ if name.startswith('test_static_'))
