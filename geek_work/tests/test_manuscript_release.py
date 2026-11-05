import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_manuscript_release as r
import test_operation_git as fixture_module


class ManuscriptReleaseTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture_module.OperationGitTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.repo=self.f.repo;self.bundle=self.f.out;self.git_pin=self.f.stage()['manifest_sha256'];self.root=self.f.f.root
        self.proposal=self.root/'release-review';self.public=self.root/'public-package';self.audit=self.root/'private-audit';self.choice=self.root/'release-decisions.json';self.select=self.root/'release-selection.json'
        self.rows=[dict(source=n,destination=n,sha256=r.m.sha((self.bundle/'preflight/sources'/n).read_bytes())) for n in ('main.tex','section.tex','bib/refs.bib')]
        self.entry='main.tex'

    def prepare(self):
        raw=r.m.encoded(dict(schema='geek-work-manuscript-release-selection-1',entry=self.entry,files=self.rows));self.select.write_bytes(raw)
        result=r.prepare(self.bundle,self.git_pin,self.repo,self.select,r.m.sha(raw),self.proposal);self.pin=result['manifest_sha256'];return result

    def decisions(self):
        spec=json.loads((self.proposal/'decisions.template.json').read_bytes());spec.update(proposal_sha256=self.pin,reviewer='Private reviewer private@example.invalid')
        for x in spec['files']:x.update(decision='allow',reason='Reviewed locally at /home/private/review')
        for x in spec['findings']:x.update(decision='acknowledge',reason='Synthetic fixture explicitly reviewed')
        return spec

    def export(self,spec=None):
        self.choice.write_bytes(r.m.encoded(spec if spec is not None else self.decisions()))
        return r.export(self.proposal,self.pin,self.repo,self.choice,r.m.sha(self.choice.read_bytes()),self.public,self.audit)

    def refresh(self,comment=None,asset=None):
        f=self.f.f
        if comment:
            for root in (f.base,f.candidate,self.repo):
                p=root/'main.tex';p.write_bytes(p.read_bytes()+comment)
        rows=json.loads(f.ops.read_bytes())['operations']
        if asset is not None:
            (f.candidate/'picture.png').write_bytes(asset);f.spec['files'].append('picture.png');rows.append(dict(id='image',op='create',kind='binary',source=None,target='picture.png'))
        self.f.cmd('add','.');self.f.cmd('commit','--allow-empty','-qm','Release fixture');self.f.commit=self.f.cmd('rev-parse','HEAD').decode().strip()
        self.f.rebuild(rows);shutil.rmtree(self.bundle);self.git_pin=self.f.stage()['manifest_sha256']
        names=['main.tex','section.tex','bib/refs.bib']+(['picture.png'] if asset is not None else [])
        self.rows=[dict(source=n,destination=n,sha256=r.m.sha((self.bundle/'preflight/sources'/n).read_bytes())) for n in names]

    def reseal(self,path):
        manifest=path/'manifest.json';x=json.loads(manifest.read_bytes());x['files']={n:r.m.sha((path/n).read_bytes()) for n in x['files']};manifest.write_bytes(r.m.encoded(x));return r.m.sha(manifest.read_bytes())

    def test_explicit_export_contains_no_private_review_or_archives(self):
        self.prepare();x=self.export();r.verify_pair(self.audit,x['audit_manifest_sha256'],self.public,x['public_manifest_sha256'],self.repo)
        self.assertEqual({p.relative_to(self.public).as_posix() for p in self.public.rglob('*') if p.is_file()},{'manifest.json','files/main.tex','files/section.tex','files/bib/refs.bib'})
        raw=b''.join(p.read_bytes() for p in self.public.rglob('*') if p.is_file());self.assertNotIn(b'private@example',raw);self.assertNotIn(b'/home/private',raw);self.assertNotIn(b'proposal_sha256',raw)
        self.assertFalse(x['privacy_verified']);self.assertFalse(x['network_publication_performed'])

    def test_rejection_or_incomplete_choices_creates_no_output(self):
        self.prepare()
        for mode in ('reject','missing','null'):
            spec=self.decisions()
            if mode=='missing':spec['files'].pop()
            else:spec['files'][0]['decision']='reject' if mode=='reject' else None
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.export(spec)
            self.assertFalse(self.audit.exists());self.assertFalse(self.public.exists())

    def test_privacy_findings_require_individual_ack_without_quoting_values(self):
        self.refresh(comment=b'% contact person@example.invalid /home/alice/project api_key=syntheticvalue123\n');self.prepare()
        report=json.loads((self.proposal/'report.json').read_bytes());self.assertEqual({x['code'] for x in report['findings']},{'email','local_path','credential_assignment'})
        self.assertNotIn('person@example',json.dumps(report['findings']))
        spec=self.decisions();spec['findings'].pop()
        with self.assertRaisesRegex(ValueError,'complete'):self.export(spec)
        self.export()

    def test_opaque_asset_needs_review_and_is_not_decoded(self):
        raw=b'\x89PNG\x00synthetic-not-a-real-image';self.refresh(asset=raw);self.prepare()
        report=json.loads((self.proposal/'report.json').read_bytes());self.assertEqual(report['findings'][0]['code'],'opaque_asset');self.assertFalse(report['asset_contents_decoded'])
        self.export();self.assertEqual((self.public/'files/picture.png').read_bytes(),raw)

    def test_private_key_marker_blocks_even_with_acknowledgment(self):
        self.refresh(asset=b'-----BEGIN PRIVATE KEY-----\nsynthetic fixture');x=self.prepare();self.assertTrue(x['export_blocked'])
        with self.assertRaisesRegex(ValueError,'release blocked'):self.export()
        self.assertFalse(self.public.exists())

    def test_omitted_dependency_blocks_export(self):
        self.rows=[x for x in self.rows if x['source']!='section.tex'];x=self.prepare();self.assertTrue(x['export_blocked'])
        with self.assertRaisesRegex(ValueError,'release blocked'):self.export()

    def test_destination_rename_and_private_path_marker(self):
        self.rows[0]['destination']='internal-paper.tex';self.entry='internal-paper.tex';self.prepare()
        report=json.loads((self.proposal/'report.json').read_bytes());self.assertEqual(report['findings'][0]['code'],'private_path_marker')
        self.export();self.assertTrue((self.public/'files/internal-paper.tex').exists());self.assertFalse((self.public/'files/main.tex').exists())

    def test_selection_requires_verified_projection_and_exact_hash(self):
        self.rows[0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SHA'):self.prepare()
        self.rows[0]['source']='not-selected.tex'
        with self.assertRaisesRegex(ValueError,'final projection'):self.prepare()
        self.assertFalse(self.proposal.exists())

    def test_duplicate_case_collision_and_unsafe_destination(self):
        original=[dict(x) for x in self.rows]
        for name in ('../bad.tex','MAIN.tex','main.tex'):
            self.rows=[dict(x) for x in original];self.rows[1]['destination']=name
            with self.subTest(name=name),self.assertRaises(ValueError):self.prepare()

    def test_resealed_report_cannot_hide_findings(self):
        self.refresh(comment=b'% person@example.invalid\n');self.prepare();p=self.proposal/'report.json';x=json.loads(p.read_bytes());x['findings']=[];p.write_bytes(r.m.encoded(x));self.pin=self.reseal(self.proposal)
        with self.assertRaisesRegex(ValueError,'proposal hashes'):self.export()

    def test_public_tamper_extra_directory_and_symlink_rejected(self):
        self.prepare();x=self.export();pin=x['public_manifest_sha256'];p=self.public/'files/main.tex';raw=p.read_bytes();p.write_bytes(raw+b'Changed')
        with self.assertRaisesRegex(ValueError,'mismatch'):r.verify_public(self.public,pin)
        p.write_bytes(raw);(self.public/'extra').mkdir()
        with self.assertRaises(ValueError):r.verify_public(self.public,pin)
        (self.public/'extra').rmdir();p.unlink();p.symlink_to(self.bundle/'preflight/sources/main.tex')
        with self.assertRaises(ValueError):r.verify_public(self.public,pin)

    def test_public_verification_needs_no_git_private_material_or_old_root(self):
        self.prepare();x=self.export();copy=self.root/'public-copy';shutil.copytree(self.public,copy)
        for folder in (self.audit,self.proposal,self.bundle,self.repo,self.public):shutil.rmtree(folder)
        with patch.object(r.g,'git',side_effect=AssertionError('No Git allowed')):
            result=r.verify_public(copy,x['public_manifest_sha256'])
        self.assertEqual(result['status'],'public_bytes_consistent');self.assertFalse(result['publication_authorized'])

    def test_audit_tamper_and_wrong_public_anchor_rejected(self):
        self.prepare();x=self.export()
        with self.assertRaisesRegex(ValueError,'binding'):r.verify_pair(self.audit,x['audit_manifest_sha256'],self.public,'0'*64,self.repo)
        p=self.audit/'receipt.json';spec=json.loads(p.read_bytes());spec['privacy_verified']=True;p.write_bytes(r.m.encoded(spec));pin=self.reseal(self.audit)
        with self.assertRaisesRegex(ValueError,'audit hashes'):r.verify_pair(self.audit,pin,self.public,x['public_manifest_sha256'],self.repo)

    def test_output_separation_existing_output_and_decision_pin(self):
        self.prepare();self.choice.write_bytes(r.m.encoded(self.decisions()));pin=r.m.sha(self.choice.read_bytes())
        for public,audit in ((self.public,self.public/'audit'),(self.repo/'public',self.audit)):
            with self.assertRaises(ValueError):r.export(self.proposal,self.pin,self.repo,self.choice,pin,public,audit)
        with self.assertRaisesRegex(ValueError,'SHA mismatch'):r.export(self.proposal,self.pin,self.repo,self.choice,'0'*64,self.public,self.audit)
        self.public.mkdir()
        with self.assertRaisesRegex(ValueError,'new output'):self.export()
        self.assertFalse(self.audit.exists())

    def test_failed_public_write_leaves_plan_not_completed_pair(self):
        self.prepare();original=r.tree.write_tree
        def fail(output,files):
            if output==self.public:output.mkdir();raise OSError('Injected public write failure')
            return original(output,files)
        with patch.object(r.tree,'write_tree',fail),self.assertRaises(OSError):self.export()
        self.assertTrue((self.audit/'manifest.json').exists());self.assertFalse((self.public/'manifest.json').exists())
        receipt=json.loads((self.audit/'receipt.json').read_bytes());self.assertEqual(receipt['record_kind'],'local_export_plan');self.assertFalse(receipt['publication_authorized'])
        with self.assertRaises(ValueError):r.verify_public(self.public,receipt['public_manifest_sha256'])

    def test_unselected_final_asset_is_never_copied_or_scanned_for_release(self):
        secret=b'NEVER_EXPORT_THIS -----BEGIN PRIVATE KEY-----'
        self.refresh(asset=secret);self.rows=[x for x in self.rows if x['source']!='picture.png']
        result=self.prepare();self.assertFalse(result['export_blocked']);self.assertEqual(result['findings'],0)
        self.export();self.assertFalse((self.public/'files/picture.png').exists())
        self.assertNotIn(secret,b''.join(p.read_bytes() for p in self.public.rglob('*') if p.is_file()))

    def test_finding_budget_and_public_manifest_shape(self):
        self.refresh(comment=b'% a@example.invalid\n');
        with patch.object(r,'MAX_FINDINGS',0),self.assertRaisesRegex(ValueError,'finding limit'):self.prepare()
        self.prepare();x=self.export();p=self.public/'manifest.json';spec=json.loads(p.read_bytes());spec['reviewer']='Must not appear';p.write_bytes(r.m.encoded(spec))
        with self.assertRaises(ValueError):r.verify_public(self.public,r.m.sha(p.read_bytes()))


if __name__=='__main__':unittest.main()
