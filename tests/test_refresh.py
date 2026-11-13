"""S07 / T30–T36: fixture-based cache, versions, retries and settings refresh."""
from pathlib import Path
from access_intake.ingest import load_document
from access_intake.worker import run_pending
from worker_support import OperationCase,SavedFactory
from support import ROOT

class RefreshS07(OperationCase):
    def finish(self,factory=None):
        factory=factory or SavedFactory();run_pending(self.store,factory,workers=1,rpm=0);return factory
    def test_t30_unchanged_success_is_reused_without_provider_call(self):
        first=self.register(1);factory=self.finish()
        self.assertEqual(self.register(1),first);self.finish(factory)
        self.assertEqual(len(factory.calls),1);self.assertEqual(len(self.store.queue()),1)
    def test_t31_changed_source_retains_old_hash_and_result(self):
        self.register(1);self.finish();production=self.production()
        self.store.register(production,self.settings);self.finish()
        current=self.store.queue()[0];self.assertEqual(current['extraction']['environment'],'production')
        history=self.store.history('IT-001.json');self.assertEqual(len(history),2)
        self.assertEqual(history[0]['source_sha256'],self.documents[0].source_sha256)
    def test_t32_model_change_refreshes_and_worker_count_does_not(self):
        self.register(1);factory=self.finish()
        changed=dict(self.settings,model='fixture-v2')
        self.store.refresh(changed);self.finish(factory)
        self.assertEqual(len(factory.calls),2);self.assertEqual(self.store.queue()[0]['configuration']['model'],'fixture-v2')
        self.store.refresh(dict(changed,workers=2));self.finish(factory);self.assertEqual(len(factory.calls),2)
    def test_t33_policy_change_refreshes_routing_with_version_history(self):
        self.register(1);self.finish();old=self.store.queue()[0]['policy_version']
        self.store.refresh(self.settings,policy={'staging_read_requires_security':True});self.finish()
        self.assertEqual(self.store.queue()[0]['owner'],'Security Review')
        self.assertNotEqual(self.store.queue()[0]['policy_version'],old)
        self.assertEqual(self.store.history('IT-001.json')[0]['owner'],'System Owner')
    def test_t34_failed_retry_after_success_is_current_and_old_success_is_history(self):
        self.register(1);self.finish();successful=self.store.queue()[0]['attempt_id']
        self.store.retry(successful,force=True);self.finish(SavedFactory(fail=self.documents[0].source_sha256))
        current=self.store.queue()[0];self.assertEqual(current['status'],'error');self.assertIsNone(current['extraction'])
        self.assertIn('retry',current['retry_command']);self.assertEqual(self.store.history('IT-001.json')[0]['owner'],'System Owner')
        calls=len(self.store.history('IT-001.json'));self.register(1);self.finish();self.assertEqual(len(self.store.history('IT-001.json')),calls)
    def test_t35_manual_retry_creates_attempt_and_rejects_stale_source(self):
        self.register(1);self.finish(SavedFactory(fail=self.documents[0].source_sha256));failed=self.store.queue()[0]['attempt_id']
        self.store.retry(failed);self.finish();self.assertEqual(len(self.store.history('IT-001.json')),2)
        self.store.register(self.production(),self.settings)
        with self.assertRaisesRegex(ValueError,'stale'):self.store.retry(failed)
    def test_t35_shared_pacing_and_cooldown_use_recorded_clock(self):
        now=[100.];self.store.clock=lambda:now[0]
        self.register(1);self.register(2);first=self.store.claim('one',rpm=60)
        self.assertIsNotNone(first);self.assertIsNone(self.store.claim('two',rpm=60))
        now[0]=101.1;self.store.cooldown('mock',2)
        self.assertIsNone(self.store.claim('two',rpm=60));now[0]=104.
        self.assertIsNotNone(self.store.claim('two',rpm=60))
    def test_t36_later_partial_batch_does_not_withdraw_prior_document(self):
        self.register(1);self.register(2);self.finish()
        path=self.folder/'IT-002.json';path.write_bytes((ROOT/'tests/inputs/IT-002.updated-purpose.json').read_bytes())
        self.store.register(load_document(path),self.settings);self.finish()
        queue={r['document_id']:r for r in self.store.queue()}
        self.assertEqual(queue['IT-001.json']['owner'],'System Owner')
        self.assertEqual(queue['IT-002.json']['extraction']['business_purpose'],'to verify the corrected settlement totals')
