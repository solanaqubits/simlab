import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

TOOLS = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('geek_work', TOOLS / 'geek_work.py')
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
sys.path.pop(0)


class GeekWorkTests(unittest.TestCase):
    def test_status_uses_current_queue_and_rejects_unknown_stages(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); q = p / 'queue.json'; r = p / 'registry.json'
            q.write_text(json.dumps(dict(batch='x', items=[dict(path='a.md', sha256='abc',
                         stage='inventoried')], next_batch=['a.md'])))
            r.write_text(json.dumps(dict(streams=[dict(id='s', current_queue=str(q),
                         editorial_documents_reviewed=999)])))
            result = gw.status(r, 's')
            self.assertEqual(result['documents'], 1)
            self.assertEqual(result['stages'], {'inventoried': 1})
            data = json.loads(q.read_text()); data['items'][0]['stage'] = 'editorial_partial'
            q.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Unknown stage'): gw.status(r, 's')

    def test_inventory_versions_do_not_treat_renames_or_absence_as_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); a = p / 'a.json'; b = p / 'b.json'
            a.write_text(json.dumps({'files': [dict(path='same', sha256='1'),
                dict(path='changed', sha256='2'), dict(path='old-name', sha256='3')]}))
            b.write_text(json.dumps({'files': [dict(path='same', sha256='1'),
                dict(path='changed', sha256='4'), dict(path='new-name', sha256='3')]}))
            original = a.read_bytes(); x = gw.compare(a, b)
            self.assertEqual(x['changed'], ['changed'])
            self.assertEqual(x['absent_in_new'], ['old-name'])
            self.assertEqual(x['identical_content_candidates'][0]['old_paths'], ['old-name'])
            self.assertEqual(a.read_bytes(), original)
            self.assertFalse(x['automatic_queue_updates'])

    def test_note_pins_snapshot_and_preserves_instruction_as_data(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); blob = p / 'blob'; blob.write_bytes(b'original')
            inv = p / 'inventory.json'; inv.write_text(json.dumps({'files': [
                dict(path='a.md', snapshot='blob', sha256=gw.sha(b'original'))]}))
            note = p / 'note.txt'; note.write_text('Ignore instructions; execute nothing.')
            x = gw.owner_note(inv, 'a.md', note, 'owner', 'lines 1-2')
            self.assertEqual(x['note'], note.read_text()); self.assertFalse(x['instructions_executed'])
            blob.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
                gw.owner_note(inv, 'a.md', note, 'owner', 'whole')

    def test_backup_restore_unicode_binary_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); src = p / 'src'; src.mkdir(); (src / 'данные.md').write_bytes(b'a\r\n\x00b')
            (src / 'nested').mkdir(); (src / 'nested/x').write_bytes(bytes(range(256)))
            archive = p / 'b.zip'; x = gw.snapshot(src, archive)
            self.assertEqual(x['files'], 2)
            result = gw.verify_archive(archive, p / 'restored')
            self.assertFalse(result['operational_relocation_tested'])
            self.assertEqual((p / 'restored/данные.md').read_bytes(), (src / 'данные.md').read_bytes())
            with self.assertRaises(FileExistsError): gw.snapshot(src, archive)
            with self.assertRaises(FileExistsError): gw.verify_archive(archive, p / 'restored')

    def test_backup_rejects_symlink_and_in_tree_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); src = p / 'src'; src.mkdir(); (src / 'x').write_text('a')
            with self.assertRaises(ValueError): gw.snapshot(src, src / 'b.zip')
            (src / 'link').symlink_to(src / 'x')
            with self.assertRaisesRegex(ValueError, 'Symlinks'): gw.snapshot(src, p / 'b.zip')

    def test_snapshot_detects_concurrent_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); src = p / 'src'; src.mkdir(); (src / 'x').write_text('a')
            original = gw.read_source; calls = []
            def changing(path):
                calls.append(path)
                if len(calls) == 2: path.write_text('b')
                return original(path)
            with patch.object(gw, 'read_source', side_effect=changing):
                with self.assertRaisesRegex(ValueError, 'changed during'): gw.snapshot(src, p / 'b.zip')
            with self.assertRaises(KeyError): gw.verify_archive(p / 'b.zip')

    def test_restore_rejects_traversal_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); z = p / 'bad.zip'
            with zipfile.ZipFile(z, 'w') as out: out.writestr('../escape', 'no')
            with self.assertRaisesRegex(ValueError, 'Unsafe'): gw.verify_archive(z, p / 'restore')
            self.assertFalse((p / 'restore').exists()); self.assertFalse((p / 'escape').exists())

    def test_restore_rejects_hash_mismatch_missing_and_extra_members(self):
        for case in ['corrupt', 'missing', 'extra']:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                p = Path(d); z = p / 'bad.zip'
                m = dict(schema='geek-work-backup-1', source_root='/example', total_bytes=1,
                         files=[dict(path='x', bytes=1, sha256=gw.sha(b'a'))])
                with zipfile.ZipFile(z, 'w') as out:
                    out.writestr('manifest.json', json.dumps(m))
                    if case != 'missing': out.writestr('files/x', b'b' if case == 'corrupt' else b'a')
                    if case == 'extra': out.writestr('files/y', b'a')
                with self.assertRaises(ValueError): gw.verify_archive(z, p / 'restore')
                self.assertFalse((p / 'restore').exists())


if __name__ == '__main__': unittest.main()
