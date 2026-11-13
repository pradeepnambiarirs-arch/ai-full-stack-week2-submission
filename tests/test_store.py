"""S05 / T24: fixture-fed transactional storage, independently expected facts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from access_intake.ingest import load_document
from support import OfflineFixtureTestCase, ROOT

class StoreT24(OfflineFixtureTestCase):
    def setUp(self):
        super().setUp()
        temporary=TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.db=Path(temporary.name)/'intake.sqlite'
        from access_intake.store import Store
        self.store_class=Store; self.store=Store(self.db)
        self.document=load_document(ROOT/self.oracle['input'])
        self.settings={'provider':'mock','model':'fixture-v1'}
        self.result=dict(document_id=self.document.document_id,source_sha256=self.document.source_sha256,response_source='mock',extraction=json.loads(self.saved_response['output_text']),error=None,**self.oracle['expected_route_for_later_steps'])
    def test_t24_records_and_current_view_survive_reopen(self):
        revision=self.store.register(self.document,self.settings)
        attempt=self.store.record_result(revision,self.result)
        reopened=self.store_class(self.db)
        current=reopened.queue()[0]
        self.assertEqual(current['attempt_id'],attempt)
        self.assertEqual(current['source_sha256'],self.document.source_sha256)
        self.assertEqual(current['extraction'],self.oracle['extraction'])
        self.assertEqual(current['configuration'],self.settings)
        self.assertTrue(current['policy_version'])
        self.assertEqual(reopened.history(self.document.document_id)[0]['attempt_id'],attempt)
    def test_t24_failure_between_insert_and_publication_rolls_back(self):
        revision=self.store.register(self.document,self.settings)
        self.store.record_result(revision,self.result)
        second=self.store.register(self.document,self.settings,force=True)
        def fail(): raise RuntimeError('injected transaction failure')
        with self.assertRaisesRegex(RuntimeError,'injected'):
            self.store.record_result(second,self.result,before_commit=fail)
        self.assertEqual(len(self.store.history(self.document.document_id)),1)
        self.assertEqual(self.store.queue()[0]['extraction'],self.oracle['extraction'])
