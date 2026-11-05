import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('chat_intake', Path(__file__).parents[1] / 'tools/chat_intake.py')
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)


class IntakeTests(unittest.TestCase):
    def test_roundtrip_unicode_crlf_no_final_newline(self):
        text = 'Вопрос\r\n\r\n\r\nλ = 2  \r\nОтвет без переноса'
        clean, mapping, removed = intake.clean_text(text)
        self.assertEqual(clean, 'Вопрос\r\n\r\nλ = 2  \r\nОтвет без переноса')
        restored = dict(zip(mapping, clean.splitlines(keepends=True)))
        restored.update((r['source_line'], r['text']) for r in removed)
        self.assertEqual(''.join(restored[n] for n in sorted(restored)), text)

    def test_code_math_and_unclosed_fences_are_preserved(self):
        for text in ('```python\n\n\nprint(1)\n```\n', '~~~\n\n\nx\n~~~\n',
                     '$$\n\n\nx=1\n$$\n', '\\[\n\n\nx\n\\]\n', '```\n\n\nunfinished'):
            with self.subTest(text=text):
                self.assertEqual(intake.clean_text(text)[0], text)

    def test_content_repetitions_prompts_and_negations_stay(self):
        text = '*User prompt: Не доказано.*\n\nResponse: Не доказано.\n\nНе доказано.\n'
        self.assertEqual(intake.clean_text(text)[0], text)

    def test_oversized_block_not_split_or_truncated(self):
        text = 'начало\n\n```lean\n' + ('x\n' * 400) + '```\n\nконец\n'
        lines = text.splitlines(keepends=True)
        chunks = [''.join(lines[a:b]) for a, b in intake.chunk_spans(text, 256)]
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(any(len(c) > 256 and c.count('```') == 2 for c in chunks))

    def test_pdf_layout_not_cleaned(self):
        text = 'A\n\n\n  B\n\f'
        self.assertEqual(intake.clean_text(text, markdown=False)[0], text)

    def test_explicit_line_splitting_preserves_unicode_crlf(self):
        text = ('Длинная строка с условием ≤ 2.\r\n' * 35) + 'конец'
        lines = text.splitlines(keepends=True)
        self.assertEqual(intake.chunk_spans(text, 256), [(0, len(lines))])
        parts = [''.join(lines[a:b]) for a, b in intake.chunk_spans(text, 256, True)]
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 256 for part in parts))
        self.assertEqual(''.join(parts), text)

    def test_line_fallback_keeps_fences_math_and_both_table_styles(self):
        blocks = [
            '```lean\n' + 'x\n' * 180 + '```\n',
            '> ```lean\n' + '> x\n' * 100 + '> ```\n',
            '$$\n' + 'x + y\n' * 80 + '$$\n',
            'a | b\n--- | ---\n' + '1 | 2\n' * 80,
            '| a | b |\n| --- | --- |\n' + '| 1 | 2 |\n' * 80,
        ]
        for block in blocks:
            with self.subTest(block=block[:20]):
                text = 'начало\n' + block + 'конец\n'
                lines = text.splitlines(keepends=True)
                parts = [''.join(lines[a:b]) for a, b in intake.chunk_spans(text, 256, True)]
                self.assertEqual(''.join(parts), text)
                self.assertTrue(any(block in part for part in parts))

    def test_fallback_does_not_cut_unclosed_fence_or_single_line(self):
        for text in ['> ~~~\n' + '> x\n' * 100, 'λ' * 700]:
            with self.subTest(text=text[:10]):
                self.assertEqual(intake.chunk_spans(text, 256, True),
                                 [(0, len(text.splitlines(keepends=True)))])

    def test_line_fallback_preparation_roundtrip_and_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); src = root / 'src'; src.mkdir()
            (src / 'a.md').write_text('строка\n' * 100)
            intake.inventory(src, root / 'store')
            rec = intake.prepare(root / 'store', 'a.md', root / 'out', 256,
                                 split_oversized_lines=True)
            self.assertEqual(rec['chunking_method'], 'line_boundary_fallback')
            self.assertTrue(rec['split_oversized_lines'])
            self.assertGreater(len(rec['chunks']), 1)
            self.assertEqual(intake.verify(root / 'store', root / 'out')['status'],
                             'byte_roundtrip_and_chunks_verified')

    def test_whole_word_typo_guard_rejects_inside_another_word(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'input.md'
            source.write_text('решения. Разбери еше видео.')
            text = source.read_text()
            spec = {'input_sha256': intake.digest(source.read_bytes()), 'review': 'test',
                    'edits': [dict(start_char=1, end_char=4, before='еше', after='ещё',
                                   whole_word=True, reason='typo')]}
            path = root / 'spec.json'; path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, 'whole-word boundary'):
                intake.edit(source, path, root / 'bad')
            self.assertFalse((root / 'bad').exists())
            start = text.index('еше видео')
            spec['edits'][0].update(start_char=start, end_char=start + 3)
            path.write_text(json.dumps(spec)); intake.edit(source, path, root / 'good')
            self.assertEqual((root / 'good/edited.md').read_text(),
                             'решения. Разбери ещё видео.')

    def test_queue_checks_history_and_missing_review(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); batch = root / 'intake-batch026'; batch.mkdir()
            previous = root / 'previous.json'; previous.write_text('{}')
            queue = {'batch': '025', 'previous_queue': str(previous),
                     'lineage': {'previous_queue': str(root / 'other.json')},
                     'items': [dict(path='a.md', sha256='a', review=str(root / 'missing.json'))]}
            path = batch / 'queue.json'; path.write_text(json.dumps(queue))
            result = intake.check_queue(path)
            self.assertEqual(result['status'], 'invalid')
            self.assertTrue(any('Batch ID' in x for x in result['issues']))
            self.assertTrue(any('Conflicting' in x for x in result['issues']))
            self.assertTrue(any('missing review' in x for x in result['issues']))

    def test_queue_checks_chunk_coverage_and_review_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); prep = root / 'prepared'; prep.mkdir()
            (prep / 'preparation.json').write_text(json.dumps({
                'source': {'sha256': 'abc'}, 'chunks': [
                    {'file': 'chunks/0001.md', 'chars': 12, 'sha256': 'chunk1'},
                    {'file': 'chunks/0002.md', 'chars': 15, 'sha256': 'chunk2'}]}))
            review = root / 'review.json'
            review.write_text(json.dumps({'source_path': 'a.md', 'source_sha256': 'abc',
                                          'chunk_path': 'chunks/0001.md',
                                          'chunk_sha256': 'chunk1'}))
            row = dict(path='a.md', sha256='abc', prepared=str(prep), reviews=[str(review)],
                       reviewed_chunks=['chunks/0001.md'], unreviewed_chunks=['chunks/0002.md'],
                       reviewed_chars=12, stage='editorial_partial_reviewed')
            path = root / 'queue.json'; path.write_text(json.dumps({'items': [row]}))
            self.assertEqual(intake.check_queue(path)['status'], 'valid')
            changed_review = json.loads(review.read_text())
            changed_review['chunk_sha256'] = 'wrong'
            review.write_text(json.dumps(changed_review))
            self.assertTrue(any('chunk hash mismatch' in x
                                for x in intake.check_queue(path)['issues']))
            changed_review['chunk_sha256'] = 'chunk1'
            review.write_text(json.dumps(changed_review))
            row.update(stage='editorial_pilot_reviewed', reviewed_chars=27,
                       reviewed_chunks=['chunks/0001.md', 'chunks/0002.md'])
            path.write_text(json.dumps({'items': [row]}))
            issues = intake.check_queue(path)['issues']
            self.assertTrue(any('partition mismatch' in x for x in issues))
            self.assertTrue(any('differ from review records' in x for x in issues))
            self.assertTrue(any('complete status' in x for x in issues))
            row.update(sha256='wrong')
            path.write_text(json.dumps({'items': [row]}))
            self.assertTrue(any('source_sha256 mismatch' in x
                                for x in intake.check_queue(path)['issues']))

    def test_end_to_end_snapshot_reconstruction_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); src = root / 'src'; src.mkdir()
            raw = '## Заголовок\n\n\nусловие ≤ 2\n'.encode()
            (src / 'one.md').write_bytes(raw); (src / 'copy.md').write_bytes(raw)
            store, out = root / 'store', root / 'out'
            inv = intake.inventory(src, store)
            self.assertEqual(len(inv['files']), 2)
            self.assertEqual(len(list((store / 'raw').iterdir())), 1)
            intake.prepare(store, 'one.md', out, 256)
            self.assertEqual(intake.verify(store, out)['status'], 'byte_roundtrip_and_chunks_verified')
            self.assertEqual((src / 'one.md').read_bytes(), raw)
            (out / 'chunks/0001.md').write_text('damaged')
            with self.assertRaises(ValueError):
                intake.verify(store, out)

    def test_refuses_overwrite_and_in_source_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); src = root / 'src'; src.mkdir(); (src / 'a.md').write_text('abc')
            with self.assertRaises(ValueError):
                intake.inventory(src, src / 'output')
            store = root / 'store'; intake.inventory(src, store)
            with self.assertRaises(FileExistsError):
                intake.inventory(src, store)

    def test_corrupt_snapshot_and_invalid_utf8_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); src = root / 'src'; src.mkdir(); (src / 'a.md').write_bytes(b'\xff')
            store = root / 'store'; inv = intake.inventory(src, store)
            self.assertIn('encoding_issue', inv['files'][0])
            with self.assertRaises(UnicodeDecodeError):
                intake.prepare(store, 'a.md', root / 'out')
            (store / inv['files'][0]['snapshot']).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                intake.prepare(store, 'a.md', root / 'out2')

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); src = root / 'src'; src.mkdir(); outside = root / 'outside'
            outside.write_text('not an export'); (src / 'link.md').symlink_to(outside)
            with self.assertRaises(ValueError):
                intake.inventory(src, root / 'out')

    def test_pdf_requires_bounded_explicit_page_range(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'raw').mkdir(); raw = b'%PDF-placeholder'
            sha = intake.digest(raw); (root / 'raw' / sha).write_bytes(raw)
            (root / 'inventory.json').write_text(json.dumps({'files': [dict(
                path='a.pdf', snapshot='raw/' + sha, sha256=sha, format='pdf', pages=100)]}))
            for pages in (None, [1, 21], [0, 2], [1, 101]):
                with self.subTest(pages=pages), self.assertRaises(ValueError):
                    intake.prepare(root, 'a.pdf', root / 'out', pages=pages)

    def test_editorial_inverse_for_multiple_unicode_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'input.md'; source.write_text('А привет! Б факт. В')
            spec = {'input_sha256': intake.digest(source.read_bytes()), 'review': 'editorial only',
                    'edits': [dict(start_char=2, end_char=10, before='привет! ', after='', reason='filler'),
                              dict(start_char=12, end_char=17, before='факт.', after='тезис.', reason='label')]}
            path = root / 'spec.json'; path.write_text(json.dumps(spec))
            rec = intake.edit(source, path, root / 'out')
            result = (root / 'out/edited.md').read_text()
            self.assertEqual(result, 'А Б тезис. В')
            for e in reversed(rec['edits']):
                result = result[:e['output_start_char']] + e['before'] + result[e['output_end_char']:]
            self.assertEqual(result, source.read_text())

    def test_editorial_stale_or_overlapping_edits_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'input.md'; source.write_text('abcdef')
            spec = {'input_sha256': intake.digest(source.read_bytes()), 'review': 'test',
                    'edits': [dict(start_char=0, end_char=3, before='abc', after='', reason='one'),
                              dict(start_char=2, end_char=4, before='cd', after='', reason='two')]}
            path = root / 'spec.json'; path.write_text(json.dumps(spec))
            with self.assertRaises(ValueError):
                intake.edit(source, path, root / 'out')
            source.write_text('changed')
            with self.assertRaises(ValueError):
                intake.edit(source, path, root / 'out')


if __name__ == '__main__':
    unittest.main()
