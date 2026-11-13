"""Consistent current snapshots and explicitly labeled request-construction evidence."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from access_intake.worker import document_from_revision
from access_intake.providers.openai import OpenAIProvider,DEFAULT_MODEL
from access_intake.providers.base import ProviderError

def sha(data):return hashlib.sha256(data).hexdigest()
def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('wb',dir=path.parent,delete=False) as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno());temporary=stream.name
    os.replace(temporary,path)
@contextmanager
def export_lock(out,exclusive=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'.export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

def request_evidence(store,current=None):
    current=current or next((row for row in store.queue() if row.get('revision_id') and row.get('extraction')),None)
    if not current:return {'observation':'no records; no provider response or example request captured'}
    revision=store.revision(current['revision_id']);document=document_from_revision(revision)
    configuration=dict(revision['configuration']) if revision['configuration'].get('provider')=='openai' else {'provider':'openai','model':DEFAULT_MODEL}
    settings=dict(configuration,_prompt_text=revision.get('prompt_text',''),_schema_text=revision.get('schema_text',''))
    def capture(request,*,timeout):raise ProviderError('capture-only')
    provider=OpenAIProvider(settings,transport=capture,credential_supplier=lambda:'REDACTED_PLACEHOLDER')
    try:provider.extract(document.message,source_sha256=document.source_sha256,configuration=configuration)
    except ProviderError as error:
        if error.code!='capture-only':raise
    evidence=dict(provider.request_evidence)
    evidence.update(observation='request-capture-only; no provider response observed',source_record_response_source=current['response_source'],source_record_configuration=current['configuration'],example_configuration=configuration)
    return evidence

def export_current(store,out,*,fault=None):
    out=Path(out)
    with export_lock(out):
        # A single read transaction in queue() freezes the pair's entire input.
        rows=store.queue()
        if any(row.get('pending') for row in rows):raise ValueError('pending desired work; resume or finish it before final export')
        rows=[{k:v for k,v in row.items() if k not in ('pending','previous_version','desired_source_sha256')} for row in rows]
        if fault:fault('snapshot')
        extractions=''.join(json.dumps(row,sort_keys=True)+'\n' for row in rows).encode()
        queue=(json.dumps(rows,indent=2,sort_keys=True)+'\n').encode()
        generation=uuid.uuid4().hex;folder=out/'.generations'/generation;folder.mkdir(parents=True)
        sample=next((row for row in rows if row.get('extraction')),None)
        evidence=(json.dumps(request_evidence(store,sample),indent=2)+'\n').encode()
        files={'extractions.jsonl':extractions,'queue.json':queue,'request-evidence.json':evidence}
        manifest={'generation':generation,'documents':len(rows),'files':{name:sha(data) for name,data in files.items()},'publication':'static database snapshot; CURRENT selects a complete generation; flat files require manifest verification'}
        manifest_bytes=(json.dumps(manifest,indent=2)+'\n').encode()
        for name,data in files.items():atomic(folder/name,data)
        atomic(folder/'manifest.json',manifest_bytes)
        atomic(out/'CURRENT',(generation+'\n').encode())
        atomic(out/'extractions.jsonl',extractions)
        if fault:fault('after_extractions')
        atomic(out/'queue.json',queue)
        atomic(out/'request-evidence.json',evidence)
        atomic(out/'manifest.json',manifest_bytes)
        return manifest

def check_export(out):
    out=Path(out)
    with export_lock(out,False):
        try:
            manifest=json.loads((out/'manifest.json').read_text())
            for name,wanted in manifest['files'].items():
                if sha((out/name).read_bytes())!=wanted:raise ValueError('export manifest mismatch; rerun export to repair interrupted publication')
            records=[json.loads(line) for line in (out/'extractions.jsonl').read_text().splitlines()]
            if records!=json.loads((out/'queue.json').read_text()):raise ValueError('queue and extraction records disagree')
            if len({row['document_id'] for row in records})!=len(records):raise ValueError('duplicate document in current export')
            return manifest
        except (OSError,KeyError,json.JSONDecodeError):raise ValueError('incomplete export; rerun export to repair publication') from None
