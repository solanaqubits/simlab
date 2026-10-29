import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_hexagon as h

URL='https://hexagonmath.org/api/v1/works?limit=1'
RSS='https://hexagonmath.org/rss/cs.LO'
STAMP='2026-10-29T10:00:00Z'


class HexagonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.work=dict(id='hexagon:2610.00001v1',identifier='2610.00001',versionNumber=1,title='Synthetic theorem',
            abstract='Unverified claim.',subject='cs.LO',authors=[dict(name='Synthetic Author')],license='CC BY 4.0',
            status='published',authorshipMode='mixed',humanUnderstanding='all',publishedAt=STAMP)
        self.doc=dict(works=[self.work],page=dict(has_more=True,next_cursor='unused'))
    def raw(self):return h.k.canonical(self.doc)
    def rss(self,link='https://hexagonmath.org/2610.00001v2'):
        return ('<rss version="2.0"><channel><item><title>Fixture</title><link>'+link+
            '</link><guid>https://hexagonmath.org/2610.00001</guid><description>&lt;script&gt;untrusted&lt;/script&gt;</description></item></channel></rss>').encode()
    def bundle(self):
        self.out=self.root/'snapshot';self.marker=h.snapshot(self.raw(),URL,STAMP,'local-snapshot',self.out)
        return self.out
    def reseal(self):
        p=self.out/'seal.json';s=h.k.load(p)
        s['files']={name:h.k.digest((self.out/name).read_bytes()) for name in h.FILES}
        p.write_bytes(h.k.canonical(s));self.marker['seal_sha256']=h.k.digest(h.k.canonical(s))

    def test_api_keeps_reported_separate(self):
        r=h.parse(self.raw(),URL)['records'][0]
        self.assertEqual(r['reported_status'],'published');self.assertEqual(r['verification_status'],'unreviewed')
        self.assertFalse(r['peer_review_verified']);self.assertFalse(r['accepted_into_knowledge_graph'])
        self.assertEqual(r['license'],'CC BY 4.0')

    def test_rss_version_from_link_not_guid(self):
        r=h.parse(self.rss(),RSS)['records'][0];self.assertEqual(r['version'],2)
        self.assertIsNone(r['license']);self.assertIsNone(r['reported_status'])

    def test_html_stays_inert_text(self):
        r=h.parse(self.rss(),RSS)['records'][0]
        self.assertEqual(r['abstract'],'<script>untrusted</script>')
        self.assertEqual(r['abstract_format'],'untrusted_html_text')

    def test_no_implicit_latest(self):
        with self.assertRaisesRegex(h.k.Refusal,'explicit_version'):h.parse(self.rss('https://hexagonmath.org/2610.00001'),RSS)

    def test_inconsistent_version(self):
        self.work['versionNumber']=2
        with self.assertRaisesRegex(h.k.Refusal,'version_mismatch'):h.parse(self.raw(),URL)

    def test_boolean_version_refused(self):
        self.work['versionNumber']=True
        with self.assertRaisesRegex(h.k.Refusal,'version_mismatch'):h.parse(self.raw(),URL)

    def test_no_float_or_duplicate_keys(self):
        for raw in [b'{"works":[],"works":[],"page":{}}',b'{"works":[],"page":{"total":1.5}}']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):h.parse(raw,URL)

    def test_duplicate_version(self):
        self.doc['works'].append(copy.deepcopy(self.work))
        with self.assertRaisesRegex(h.k.Refusal,'duplicate_version'):h.parse(self.raw(),URL.replace('limit=1','limit=2'))

    def test_response_count_bound(self):
        self.doc['works'].append(copy.deepcopy(self.work))
        with self.assertRaisesRegex(h.k.Refusal,'record_limit'):h.parse(self.raw(),URL)

    def test_byte_bound(self):
        with self.assertRaisesRegex(h.k.Refusal,'byte_limit'):h.parse(b'x'*(h.MAX_BYTES+1),URL)

    def test_url_allowlist(self):
        urls=['http://hexagonmath.org/rss/all','https://hexagonmath.org.evil/rss/all',
              'https://user@hexagonmath.org/rss/all','https://hexagonmath.org:443/rss/all',
              'https://hexagonmath.org/api/v1/submissions','https://hexagonmath.org/api/v1/works',
              URL+'&token=secret',URL+'&limit=2','https://hexagonmath.org/api/v1/works?limit=99',
              'https://hexagonmath.org/rss/all?redirect=evil','https://hexagonmath.org/rss/%2e%2e',URL+'#fragment']
        for url in urls:
            with self.subTest(url=url),self.assertRaises(ValueError):h.source_url(url)

    def test_rss_external_record_refused(self):
        with self.assertRaisesRegex(h.k.Refusal,'record_origin'):h.parse(self.rss('https://evil/2610.00001v1'),RSS)

    def test_xml_entities_forbidden(self):
        raw=b'<!DOCTYPE rss [<!ENTITY x "x">]>'+self.rss()
        with self.assertRaisesRegex(h.k.Refusal,'xml_declarations'):h.parse(raw,RSS)

    def test_xml_null_encoding_refused(self):
        with self.assertRaises(ValueError):h.parse(self.rss().decode().encode('utf-16'),RSS)

    def test_xml_depth_bound(self):
        raw=b'<rss version="2.0"><channel>'+b'<x>'*20+b'</x>'*20+b'</channel></rss>'
        with self.assertRaisesRegex(h.k.Refusal,'xml_structure_limit'):h.parse(raw,RSS)

    def test_empty_feed_valid(self):
        self.assertEqual(h.parse(b'<rss version="2.0"><channel/></rss>',RSS)['records'],[])

    def test_unknown_schema_refused(self):
        with self.assertRaisesRegex(h.k.Refusal,'api_shape'):h.parse(b'{"items":[]}',URL)

    def test_snapshot_replay(self):
        self.bundle();r=h.verify(self.out,self.marker['seal_sha256'])
        self.assertEqual(r,h.parse(self.raw(),URL));self.assertFalse(r['complete_catalog'])

    def test_exclusive_snapshot(self):
        self.bundle()
        with self.assertRaises(FileExistsError):h.snapshot(self.raw(),URL,STAMP,'local-snapshot',self.out)

    def test_utc_required(self):
        with self.assertRaisesRegex(h.k.Refusal,'utc_timestamp'):h.snapshot(self.raw(),URL,'2026-10-29T00:00:00','local-snapshot',self.root/'out')

    def test_raw_tamper(self):
        self.bundle();(self.out/'response.raw').write_bytes(b'{}')
        with self.assertRaisesRegex(h.k.Refusal,'file_hash'):h.verify(self.out,self.marker['seal_sha256'])

    def test_resealed_promotion_refused(self):
        self.bundle();p=self.out/'records.json';r=h.k.load(p);r['records'][0]['verification_status']='proved';p.write_bytes(h.k.canonical(r));self.reseal()
        with self.assertRaisesRegex(h.k.Refusal,'projection_changed'):h.verify(self.out,self.marker['seal_sha256'])

    def test_external_anchor(self):
        self.bundle()
        with self.assertRaisesRegex(h.k.Refusal,'seal_anchor'):h.verify(self.out,'a'*64)

    def test_bundle_extra_file(self):
        self.bundle();(self.out/'extra').write_text('x')
        with self.assertRaisesRegex(h.k.Refusal,'file_set'):h.verify(self.out,self.marker['seal_sha256'])

    def test_symlink_snapshot(self):
        self.bundle();link=self.root/'link';link.symlink_to(self.out)
        with self.assertRaisesRegex(h.k.Refusal,'bundle_directory'):h.verify(link,self.marker['seal_sha256'])

    def test_metadata_changes_same_version(self):
        old=h.parse(self.raw(),URL);self.work['status']='withdrawn';new=h.parse(self.raw(),URL)
        self.assertEqual(h.diff(old,new)['changed_same_version'],['hexagon:2610.00001v1'])

    def test_new_version_and_absence_not_withdrawal(self):
        old=h.parse(self.raw(),URL);self.work.update(id='hexagon:2610.00001v2',versionNumber=2);new=h.parse(self.raw(),URL)
        r=h.diff(old,new);self.assertEqual(r['added_versions'],['hexagon:2610.00001v2']);self.assertFalse(r['absence_means_withdrawal'])

    def test_get_no_credentials_and_no_pagination(self):
        response=MagicMock();response.status=200;response.read.return_value=self.raw()
        response.getheader.side_effect=lambda key,default=None:{'Content-Type':'application/json'}.get(key,default)
        conn=MagicMock();conn.getresponse.return_value=response
        with patch.object(h.http.client,'HTTPSConnection',return_value=conn) as create:
            self.assertEqual(h.fetch(URL),self.raw())
        create.assert_called_once_with('hexagonmath.org',timeout=20)
        args,kwargs=conn.request.call_args;self.assertEqual(args,('GET','/api/v1/works?limit=1'))
        self.assertNotIn('Authorization',kwargs['headers']);self.assertNotIn('Cookie',kwargs['headers'])
        conn.request.assert_called_once();conn.close.assert_called_once()

    def test_redirect_and_403_not_followed(self):
        for status in (302,403,429):
            conn=MagicMock();conn.getresponse.return_value.status=status
            with patch.object(h.http.client,'HTTPSConnection',return_value=conn),self.assertRaisesRegex(h.k.Refusal,'http_status'):
                h.fetch(URL)
            conn.request.assert_called_once();conn.close.assert_called_once()
