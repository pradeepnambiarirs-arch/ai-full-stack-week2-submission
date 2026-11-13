"""S10 / T42–T45: consistent current artifacts, source-grounded scoring and evidence."""
import json
from access_intake.ingest import load_document
from worker_support import OperationCase
from support import ROOT,MOCKS,read_json

class ArtifactsS10(OperationCase):
    def setUp(self):
        super().setUp()
        from access_intake.artifacts import export_current,check_export,request_evidence
        from access_intake.accuracy import compare_records
        self.export=export_current;self.check=check_export;self.evidence=request_evidence;self.compare=compare_records
        self.expected=read_json(ROOT/'tests/expected/source-facts.json')['cases']
        self.record=read_json(MOCKS/'scoring-correct.json')[0]
        self.revision=self.register(1);self.store.record_result(self.revision,self.record);self.out=self.folder/'deliverables'
    def test_t42_consistent_export_and_separate_history(self):
        self.export(self.store,self.out);manifest=self.check(self.out)
        actual=[json.loads(line) for line in (self.out/'extractions.jsonl').read_text().splitlines()]
        queue=read_json(self.out/'queue.json');self.assertEqual(actual,queue);self.assertEqual(len(actual),1)
        self.assertEqual(actual[0]['extraction'],self.oracle['extraction']);self.assertEqual(manifest['documents'],1)
        self.assertTrue((self.out/'CURRENT').exists())
        self.store.register(self.documents[0],self.settings,force=True)
        with self.assertRaisesRegex(ValueError,'pending'):self.export(self.store,self.out)
    def test_t42_interrupted_flat_publication_is_detected_and_repairable(self):
        self.export(self.store,self.out)
        document=self.production();revision=self.store.register(document,self.settings)
        response=read_json(MOCKS/'IT-001.production.json')
        result=dict(self.record,extraction=json.loads(response['output_text']),source_sha256=document.source_sha256,owner='Security Review',next_action='review-risk-then-owner')
        self.store.record_result(revision,result)
        def fail(stage):
            if stage=='after_extractions':raise RuntimeError('simulated export interruption')
        with self.assertRaises(RuntimeError):self.export(self.store,self.out,fault=fail)
        with self.assertRaises(ValueError):self.check(self.out)
        self.export(self.store,self.out);self.check(self.out)
    def test_t43_source_corpus_and_complete_case_scores_are_independent(self):
        actual=read_json(MOCKS/'scoring-correct.json');report=self.compare(actual,{k:self.expected[k] for k in ['O01','O02']})
        self.assertEqual((report['matches'],report['denominator']),(24,24));self.assertEqual(report['route_matches'],2)
        self.assertEqual(len(self.expected),21)
    def test_t44_denominators_factual_errors_and_failed_null_slots(self):
        expected={k:self.expected[k] for k in ['O01','O02']}
        wrong=self.compare(read_json(MOCKS/'scoring-wrong-environment.json'),expected)
        self.assertEqual((wrong['matches'],wrong['denominator']),(23,24));self.assertEqual(wrong['factual_errors'][0]['field'],'environment')
        wording=self.compare(read_json(MOCKS/'scoring-paraphrase.json'),expected)
        self.assertEqual(wording['matches'],23);self.assertEqual(wording['factual_errors'],[]);self.assertTrue(wording['manual_review'])
        error=self.compare(read_json(MOCKS/'scoring-error.json'),{k:self.expected[k] for k in ['O09','O02']})
        self.assertEqual((error['matches'],error['denominator']),(12,24))
    def test_t45_captured_request_evidence_is_redacted_and_not_live(self):
        evidence=self.evidence(self.store)
        self.assertIn('no provider response',evidence['observation'])
        request=evidence['request'];self.assertEqual(request['headers']['Authorization'],'[REDACTED]')
        self.assertEqual(request['body']['model'],'gpt-5.4-mini-2026-03-17');self.assertTrue(evidence['response_handling'])
