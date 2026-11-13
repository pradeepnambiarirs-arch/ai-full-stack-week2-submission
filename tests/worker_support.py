"""Saved-response provider and temporary store support for operating-context tests."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from access_intake.ingest import load_document
from support import OfflineFixtureTestCase, ROOT, MOCKS, read_json

class SavedFactory:
    response_source='mock'
    def __init__(self,*,block=None,started=None,release=None,fail=None):
        self.bindings=read_json(MOCKS/'worker-fixtures.json');self.block=block;self.started=started;self.release=release;self.fail=fail;self.calls=[]
    def __call__(self,configuration): return self
    def extract(self,message,*,source_sha256,configuration):
        self.calls.append(source_sha256)
        if source_sha256==self.fail:
            descriptor=read_json(MOCKS/'provider-error.json');raise TimeoutError(descriptor['code'])
        if source_sha256==self.block:
            descriptor=read_json(MOCKS/'IT-002.delayed.json');assert descriptor['behavior']=='barrier'
            self.started.set()
            if not self.release.wait(5):raise TimeoutError('test barrier expired')
        return read_json(MOCKS/self.bindings[source_sha256]['response_file'])

class OperationCase(OfflineFixtureTestCase):
    def setUp(self):
        super().setUp();temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name);self.db=self.folder/'store.sqlite'
        from access_intake.store import Store
        self.store=Store(self.db);self.settings={'provider':'mock','model':'fixture-v1'}
        self.documents=[load_document(ROOT/f'materials/requests/IT-{n:03}.json') for n in (1,2,3)]
    def register(self,n):return self.store.register(self.documents[n-1],self.settings)
    def production(self):
        path=self.folder/'updated'/'IT-001.json';path.parent.mkdir()
        path.write_bytes((ROOT/'tests/inputs/IT-001.production.json').read_bytes());return load_document(path)
