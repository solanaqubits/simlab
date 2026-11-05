import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_operation_git as g
import test_operation_preflight as fixture_module


class OperationGitTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.OperationPreflightTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;f.make(True);self.f=f
        self.pin=f.check()['manifest_sha256'];self.repo=f.root/'git-project';shutil.copytree(f.base,self.repo)
        (self.repo/'unrelated.txt').write_bytes(b'Keep me\n')
        self.cmd('init','--template=');self.cmd('config','user.name','Synthetic');self.cmd('config','user.email','fixture@example.invalid')
        self.cmd('add','.');self.cmd('commit','-qm','Synthetic baseline');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        self.out=f.root/'git-bundle'

    def cmd(self,*args,data=None):
        return subprocess.run(['git','-C',str(self.repo),*args],input=data,check=True,capture_output=True,env=g.git_environment()).stdout

    def stage(self):return g.stage(self.f.out,self.pin,self.repo,self.commit,self.out)

    def snapshot(self):
        return {p.relative_to(self.repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.repo.rglob('*') if p.is_file()}

    def reseal(self):
        p=self.out/'manifest.json';x=json.loads(p.read_bytes());x['files']={n:g.m.sha((self.out/n).read_bytes()) for n in x['files']};raw=g.m.encoded(x);p.write_bytes(raw);return g.m.sha(raw)

    def test_stage_and_replay_leave_source_unchanged(self):
        before=self.snapshot();r=self.stage();self.assertEqual(r['status'],'patch_ready')
        self.assertEqual(before,self.snapshot());self.assertTrue(g.verify(self.out,r['manifest_sha256'],self.repo)['reproduced']);self.assertEqual(before,self.snapshot())
        patch_bytes=(self.out/'patch.diff').read_bytes();self.assertIn(b'a/refs.bib',patch_bytes);self.assertIn(b'b/bib/refs.bib',patch_bytes);self.assertNotIn(b'unrelated.txt',patch_bytes)

    def test_live_dirty_files_and_staged_index_are_not_claimed_checked(self):
        (self.repo/'main.tex').write_bytes(b'Live edit');self.cmd('add','main.tex');(self.repo/'refs.bib').write_bytes(b'Another live edit')
        before=self.snapshot();self.stage();self.assertEqual(before,self.snapshot())
        result=json.loads((self.out/'receipt.json').read_bytes());self.assertIn('not live worktree',result['limits'])

    def test_wrong_base_and_missing_additional_dependency_rejected(self):
        (self.repo/'section.tex').unlink();self.cmd('add','-u');self.cmd('commit','-qm','Remove selected dependency');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'GIT_BASE_MISMATCH'):self.stage()
        self.assertFalse(self.out.exists())

    def test_occupied_rename_destination_rejected(self):
        (self.repo/'bib').mkdir();(self.repo/'bib/refs.bib').write_bytes(b'Occupied');self.cmd('add','.');self.cmd('commit','-qm','Occupied');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'expected absence'):self.stage()
        self.assertFalse(self.out.exists())

    def test_directory_or_symlink_is_not_regular_baseline(self):
        (self.repo/'section.tex').unlink();(self.repo/'section.tex').symlink_to('main.tex');self.cmd('add','.');self.cmd('commit','-qm','Symlink');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'regular Git blob'):self.stage()

    def test_parent_file_blocks_new_destination(self):
        (self.repo/'bib').write_bytes(b'Collision');self.cmd('add','.');self.cmd('commit','-qm','File ancestor');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'parent is not a Git directory'):self.stage()

    def test_commit_pin_is_real_commit_not_ref_or_tree(self):
        for commit in ('HEAD','f'*40,self.cmd('rev-parse','HEAD^{tree}').decode().strip()):
            with self.subTest(commit=commit),self.assertRaises(ValueError):g.stage(self.f.out,self.pin,self.repo,commit,self.out)
        self.assertFalse(self.out.exists())

    def test_warning_preflight_rejects_before_output(self):
        self.f.make(False);self.pin=self.f.check()['manifest_sha256']
        with self.assertRaisesRegex(ValueError,'review required'):self.stage()
        self.assertFalse(self.out.exists())

    def test_resealed_patch_and_receipt_rejected(self):
        self.stage()
        for name in ('patch.diff','receipt.json'):
            p=self.out/name;original=p.read_bytes()
            if name=='patch.diff':p.write_bytes(original+b'Forged\n')
            else:
                x=json.loads(original);x['result_tree']='1'*40;p.write_bytes(g.m.encoded(x))
            pin=self.reseal()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'reproduction mismatch'):g.verify(self.out,pin,self.repo)
            p.write_bytes(original);self.reseal()

    def test_exact_archive_set_anchor_and_separation(self):
        r=self.stage()
        with self.assertRaisesRegex(ValueError,'anchor'):g.verify(self.out,'0'*64,self.repo)
        (self.out/'extra').mkdir()
        with self.assertRaises(ValueError):g.verify(self.out,r['manifest_sha256'],self.repo)
        with self.assertRaises(ValueError):g.stage(self.f.out,self.pin,self.repo,self.commit,self.repo/'output')

    def test_git_environment_blocks_inherited_overrides(self):
        with patch.dict(os.environ,{'GIT_INDEX_FILE':'/bad','GIT_OBJECT_DIRECTORY':'/bad','GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':'bad'}):
            env=g.git_environment();self.assertNotIn('GIT_INDEX_FILE',env);self.assertNotIn('GIT_CONFIG_COUNT',env);self.stage()

    def test_relocation_uses_another_repository_with_same_commit(self):
        r=self.stage();copy=self.f.root/'copy';shutil.copytree(self.repo,copy);shutil.rmtree(self.repo)
        moved=self.f.root/'moved';shutil.move(str(self.out),moved);shutil.rmtree(self.f.out)
        self.assertTrue(g.verify(moved,r['manifest_sha256'],copy)['reproduced'])

    def test_executable_rename_preserves_mode(self):
        self.cmd('update-index','--chmod=+x','refs.bib');self.cmd('commit','-qm','Executable bibliography');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        self.stage();patch_bytes=(self.out/'patch.diff').read_bytes();self.assertIn(b'new file mode 100755',patch_bytes)

    def rebuild(self,rows,reject=False):
        f=self.f
        for p in (f.proposal,f.decision,f.out):shutil.rmtree(p)
        raw=g.m.encoded(dict(schema='geek-work-file-operations-1',operations=rows));f.ops.write_bytes(raw)
        p=g.pre.ops.propose(f.base,f.candidate,f.ops,g.m.sha(raw),'synthetic','fixture',f.proposal)
        raw=g.m.encoded(dict(schema='geek-work-file-operation-selection-1',proposal_sha256=p['manifest_sha256'],reviewer='synthetic',decisions=[dict(operation_id=r['id'],decision='confirm' if r['op']=='guard' else 'reject' if reject else 'accept',reason='fixture') for r in rows]))
        choice=f.root/'choices.json';choice.write_bytes(raw)
        d=g.pre.ops.decide(f.proposal,p['manifest_sha256'],f.base,choice,g.m.sha(raw),f.decision);f.decision_anchor=d['manifest_sha256']
        self.pin=f.check()['manifest_sha256']

    def test_binary_create_delete_and_unrelated_file_preserved(self):
        old=b'old\x00asset';new=b'new\x00asset'
        (self.f.base/'old.png').write_bytes(old);(self.repo/'old.png').write_bytes(old);(self.f.candidate/'new.png').write_bytes(new)
        self.cmd('add','.');self.cmd('commit','-qm','Binary baseline');self.commit=self.cmd('rev-parse','HEAD').decode().strip()
        rows=json.loads(self.f.ops.read_bytes())['operations']+[
            dict(id='delete-image',op='delete',kind='binary',source='old.png',target=None),
            dict(id='create-image',op='create',kind='binary',source=None,target='new.png')]
        self.f.spec['files'].append('new.png');self.rebuild(rows)
        before=self.snapshot();r=self.stage();self.assertEqual(before,self.snapshot())
        patch_bytes=(self.out/'patch.diff').read_bytes();self.assertIn(b'GIT binary patch',patch_bytes);self.assertIn(b'new file mode 100644',patch_bytes)
        # A disposable independent copy receives the exported patch for byte assertions.
        copy=self.f.root/'applied';shutil.copytree(self.repo,copy)
        subprocess.run(['git','-C',str(copy),'update-index','--refresh'],check=True,capture_output=True,env=g.git_environment())
        r_apply=subprocess.run(['git','-C',str(copy),'apply','--index',str(self.out/'patch.diff')],capture_output=True,env=g.git_environment());self.assertEqual(r_apply.returncode,0,r_apply.stderr)
        self.assertEqual((copy/'new.png').read_bytes(),new);self.assertFalse((copy/'old.png').exists());self.assertEqual((copy/'unrelated.txt').read_bytes(),b'Keep me\n')
        tree=subprocess.check_output(['git','-C',str(copy),'write-tree'],env=g.git_environment()).decode().strip();self.assertEqual(tree,r['result_tree'])

    def test_no_changes_is_explicit(self):
        self.f.spec['files']=['main.tex','section.tex','refs.bib']
        self.rebuild(json.loads(self.f.ops.read_bytes())['operations'],reject=True)
        r=self.stage();self.assertEqual(r['status'],'no_changes');self.assertEqual((self.out/'patch.diff').read_bytes(),b'')
        self.assertEqual(g.verify(self.out,r['manifest_sha256'],self.repo)['status'],'no_changes')

    def test_git_failure_and_patch_limit_create_no_archive(self):
        with patch.object(g,'MAX_PATCH',8),self.assertRaisesRegex(ValueError,'output byte limit'):self.stage()
        self.assertFalse(self.out.exists())
        with patch.object(g.shutil,'which',return_value=None),self.assertRaisesRegex(ValueError,'Git executable'):self.stage()
        self.assertFalse(self.out.exists())


if __name__=='__main__':unittest.main()
