"""Resumable shared workers; model calls run outside SQLite transactions."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import uuid
from access_intake.ingest import SourceDocument
from access_intake.processing import process_document,error_record
from access_intake.validation import DEFAULT_SCHEMA_PATH

def document_from_revision(job):
    exported=json.loads(job['source'].decode('utf-8'))
    return SourceDocument(job['document_id'],job['source'],job['source_sha256'],exported['message'],{k:v for k,v in exported.items() if k!='message'})

def run_pending(store,provider_factory,*,workers=4,rpm=0,lease_seconds=120,stop_event=None):
    if workers<1:raise ValueError('workers must be positive')
    store.recover();stop_event=stop_event or threading.Event()
    def work():
        identity=uuid.uuid4().hex
        while not stop_event.is_set():
            job=store.claim(identity,lease_seconds=lease_seconds,max_inflight=workers,rpm=rpm)
            if job is None:
                if not store.pending():return
                store.recover();stop_event.wait(.02);continue
            document=document_from_revision(job);settings=job['configuration'];done=threading.Event()
            def heartbeat():
                while not done.wait(min(10,max(.05,lease_seconds/3))):
                    if not store.renew(job['id'],job['token'],lease_seconds):return
            keeper=threading.Thread(target=heartbeat,daemon=True);keeper.start()
            try:
                provider_settings=dict(settings)
                if settings.get('provider','mock')!='mock':provider_settings.update(_prompt_text=job.get('prompt_text',''),_schema_text=job.get('schema_text',''))
                provider=provider_factory(provider_settings)
                result=process_document(document,provider=provider,configuration=settings,schema_path=store.schema_snapshot(job),policy=job['policy'])
                if result['error'] and getattr(provider,'retry_after',0):store.cooldown(settings.get('provider','mock'),provider.retry_after)
            except Exception:
                source='mock' if settings.get('provider','mock')=='mock' else settings.get('provider','openai')+'/'+settings.get('model','unknown')
                result=error_record(document,source,'processing failed; inspect configuration and retry extraction')
            finally:done.set();keeper.join()
            store.record_result(job['id'],result,token=job['token'])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(work) for _ in range(workers)]
        try:
            for future in futures:future.result()
        except KeyboardInterrupt:
            stop_event.set();raise
