import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS=Path(__file__).parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
from geek_work_ranges import prepared_views, range_coverage, RANGE_SCHEMA
import chat_intake
import geek_work
import geek_work_finalize as tx
sys.path.pop(0)


def example():
    ranges=[dict(prepared=f'/tmp/range-{i}',reviews=[],reviewed_chunks=['chunks/0001.md'],
                 unreviewed_chunks=[],reviewed_chars=3) for i in (1,2)]
    row=dict(path='a.pdf',sha256='a'*64,stage='editorial_pilot_reviewed',range_schema=RANGE_SCHEMA,
             prepared_ranges=ranges,document_review_complete=True,**ranges[-1])
    preps={r['prepared']:dict(source=dict(pages=2),pdf_pages=[dict(page=i)],
                            chunks=[dict(file='chunks/0001.md',chars=3)]) for i,r in enumerate(ranges,1)}
    return row,preps


class PreparedRangesTests(unittest.TestCase):
    def test_two_ranges_counted_once_each(self):
        row,preps=example();views=prepared_views(row)
        self.assertEqual(len(views),2)
        c=range_coverage(row,preps)
        self.assertTrue(c['complete_recorded_coverage'])
        self.assertEqual(c['prepared_chunks'],2)
        self.assertFalse(c['semantic_review'])

    def test_missing_old_range_rejects_completed_document(self):
        row,preps=example();row['prepared_ranges']=row['prepared_ranges'][1:]
        with self.assertRaisesRegex(ValueError,'missing ranges'):range_coverage(row,preps)

    def test_top_and_canonical_divergence_rejected(self):
        row,_=example();row['reviews']=['/tmp/made-up.json']
        with self.assertRaisesRegex(ValueError,'mismatch'):prepared_views(row)

    def test_duplicate_preparation_rejected(self):
        row,_=example();row['prepared_ranges'].append(copy.deepcopy(row['prepared_ranges'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):prepared_views(row)

    def test_overlapping_page_maps_rejected(self):
        row,preps=example();preps['/tmp/range-2']['pdf_pages']=[dict(page=1)]
        with self.assertRaisesRegex(ValueError,'Overlapping'):range_coverage(row,preps)

    def test_source_page_totals_must_match(self):
        row,preps=example();preps['/tmp/range-2']['source']['pages']=3
        with self.assertRaisesRegex(ValueError,'totals'):range_coverage(row,preps)

    def test_unknown_schema_and_ambiguous_authorities(self):
        row,_=example();row['additional_prepared_ranges']=[{}]
        with self.assertRaisesRegex(ValueError,'Ambiguous'):prepared_views(row)
        row['range_schema']='new-unknown'
        with self.assertRaisesRegex(ValueError,'Unknown'):prepared_views(row)

    def test_partial_review_does_not_claim_page_complete(self):
        row,preps=example();row['stage']='extraction_review_required';row['document_review_complete']=False
        row['prepared_ranges'][0]['reviewed_chunks']=[]
        row['prepared_ranges'][0]['unreviewed_chunks']=['chunks/0001.md']
        c=range_coverage(row,preps)
        self.assertEqual(c['pages_with_all_chunks_reviewed'],1)
        self.assertFalse(c['complete_recorded_coverage'])

    def test_legacy_view_unchanged(self):
        row=dict(prepared='/tmp/prepared',path='a.md')
        self.assertEqual(prepared_views(row),[row]);self.assertIsNone(range_coverage(row,{}))

    def test_finalizer_checks_old_range_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            pp=Path(tmp);original='abc';h=tx.digest(original.encode())
            (pp/'edited.md').write_text(original)
            (pp/'edits.json').write_text(json.dumps(dict(input_sha256=h,output_sha256=h,edits=[])))
            (pp/'chunk.md').write_text(original)
            review=dict(source_path='other.pdf',source_sha256='b'*64,chunk_path='chunk.md',
                        chunk_sha256=h,chunk_chars=3)
            ref=pp/'review.json';ref.write_text(json.dumps(review))
            row=dict(path='a.pdf',sha256='a'*64,reviews=[str(ref)],reviewed_chunks=['chunk.md'])
            prep=dict(chunks=[dict(file='chunk.md',sha256=h)])
            with self.assertRaisesRegex(ValueError,'source mismatch'):tx.check_reviews(row,pp,prep,{})
            review.update(source_path='a.pdf',source_sha256='a'*64,chunk_sha256='f'*64)
            ref.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError,'chunk hash'):tx.check_reviews(row,pp,prep,{})

    def test_lineage_cannot_keep_stale_hash_or_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);old=p/'previous.json';old.write_text(json.dumps(dict(batch=10,items=[])))
            q=dict(batch=11,items=[],previous_queue=str(old),lineage=dict(batch=10,
                previous_queue=str(old),previous_batch=9,previous_queue_sha256='0'*64))
            path=p/'queue.json';path.write_text(json.dumps(q))
            check=chat_intake.check_queue(path)
            self.assertEqual(check['status'],'invalid')
            self.assertEqual(len(check['issues']),3)
            q['lineage'].update(batch=11,previous_batch=10,previous_queue_sha256=tx.digest(old.read_bytes()))
            path.write_text(json.dumps(q));self.assertEqual(chat_intake.check_queue(path)['status'],'valid')

    def test_check_queue_rejects_unseen_prior_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);row,preps=example()
            for i,r in enumerate(row['prepared_ranges'],1):
                pp=p/f'prep{i}';pp.mkdir();prep=preps[r['prepared']]
                prep['source']['sha256']=row['sha256'];prep['chunks'][0]['sha256']='c'*64
                r['prepared']=str(pp);(pp/'preparation.json').write_text(json.dumps(prep))
                review=pp/'review.json';review.write_text(json.dumps(dict(source_path='a.pdf',source_sha256=row['sha256'],chunk_path='chunks/0001.md',chunk_sha256='c'*64)))
                r['reviews']=[str(review)]
            for k in ('prepared','reviews','reviewed_chunks','unreviewed_chunks','reviewed_chars'):
                row[k]=copy.deepcopy(row['prepared_ranges'][-1][k])
            # It is a structurally complete queue until the old range loses a review.
            queue=p/'queue.json';queue.write_text(json.dumps(dict(items=[row])))
            self.assertEqual(chat_intake.check_queue(queue)['status'],'valid')
            row['prepared_ranges'][0]['reviews']=[];queue.write_text(json.dumps(dict(items=[row])))
            r=chat_intake.check_queue(queue)
            self.assertEqual(r['status'],'invalid')
            self.assertTrue(any('reviewed chunks differ' in x for x in r['issues']))


if __name__=='__main__':unittest.main()
