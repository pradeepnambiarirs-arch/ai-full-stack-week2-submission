"""S06 / T25–T29: partial visibility, failures, leases and shared operators."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import threading
import time
from access_intake.processing import process_document
from worker_support import OperationCase, SavedFactory

def operator(db,connection,hold=False):
    from access_intake.store import Store
    from access_intake.worker import run_pending
    store=Store(db)
    if hold:
        claim=store.claim('child',max_inflight=2,rpm=0)
        connection.send(claim['id'] if claim else None)
    else:
        run_pending(store,SavedFactory(),workers=1,rpm=0);connection.send(True)
    connection.close()

class WorkersS06(OperationCase):
    def setUp(self):
        super().setUp()
        from access_intake.worker import run_pending
        self.run=run_pending
    def test_t25_completed_record_visible_while_other_response_is_blocked(self):
        self.register(2);self.register(1)
        started=threading.Event();release=threading.Event();self.addCleanup(release.set)
        factory=SavedFactory(block=self.documents[1].source_sha256,started=started,release=release)
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(self.run,self.store,factory,workers=2,rpm=0)
            try:
                self.assertTrue(started.wait(2))
                end=time.monotonic()+2
                while time.monotonic()<end and not any(r.get('extraction') for r in self.store.queue()):time.sleep(.01)
                ready=next(r for r in self.store.queue() if r['document_id']=='IT-001.json')
                self.assertEqual(ready['owner'],'System Owner');self.assertFalse(future.done())
            finally:release.set()
            future.result(timeout=3)
    def test_t26_provider_failure_is_visible_and_other_documents_finish(self):
        for n in (1,2,3):self.register(n)
        self.run(self.store,SavedFactory(fail=self.documents[1].source_sha256),workers=3,rpm=0)
        queue={r['document_id']:r for r in self.store.queue()}
        self.assertEqual(queue['IT-001.json']['owner'],'System Owner')
        self.assertEqual(queue['IT-003.json']['status'],'needs-information')
        self.assertEqual(queue['IT-002.json']['status'],'error');self.assertIsNone(queue['IT-002.json']['extraction'])
    def test_t27_expired_claim_is_recorded_and_resumed_from_persisted_source(self):
        now=[100.];self.store.clock=lambda:now[0]
        revision=self.register(1);old=self.store.claim('terminated',lease_seconds=1,rpm=0)
        now[0]=102.;self.assertEqual(self.store.recover(),1)
        self.assertIn('interrupted',self.store.history('IT-001.json')[0]['error'])
        self.run(self.store,SavedFactory(),workers=1,rpm=0)
        result=self.store.queue()[0];self.assertEqual(result['owner'],'System Owner')
        self.assertIsNone(self.store.record_result(revision,result,token=old['token']))
    def test_t28_overlapping_operator_processes_leave_one_current_result_each(self):
        for n in (1,2,3):self.register(n)
        ctx=multiprocessing.get_context('fork');children=[]
        for _ in range(2):
            receiver,sender=ctx.Pipe(False);process=ctx.Process(target=operator,args=(self.db,sender));process.start();sender.close();children.append((process,receiver))
        for child,pipe in children:
            child.join(5);self.assertFalse(child.is_alive());self.assertEqual(child.exitcode,0);self.assertTrue(pipe.recv());pipe.close()
        self.assertEqual(len(self.store.queue()),3)
        for doc in self.documents:self.assertEqual(len(self.store.history(doc.document_id)),1)
    def test_t28_global_claim_limit_is_shared_between_processes(self):
        for n in (1,2,3):self.register(n)
        ctx=multiprocessing.get_context('fork');claims=[]
        for _ in range(3):
            receiver,sender=ctx.Pipe(False);child=ctx.Process(target=operator,args=(self.db,sender,True));child.start();sender.close();child.join(3)
            self.assertEqual(child.exitcode,0);claims.append(receiver.recv());receiver.close()
        self.assertEqual(len([x for x in claims if x is not None]),2)
        self.assertEqual(len(set(x for x in claims if x is not None)),2)
    def test_t29_old_generation_cannot_overwrite_new_source(self):
        first=self.register(1);old=self.store.claim('old',rpm=0)
        production=self.production();new=self.store.register(production,self.settings);claim=self.store.claim('new',rpm=0)
        factory=SavedFactory()
        current=process_document(production,provider=factory,configuration=self.settings)
        self.store.record_result(new,current,token=claim['token'])
        stale=process_document(self.documents[0],provider=factory,configuration=self.settings)
        self.store.record_result(first,stale,token=old['token'])
        self.assertEqual(self.store.queue()[0]['extraction']['environment'],'production')
        self.assertEqual(len(self.store.history('IT-001.json')),2)
