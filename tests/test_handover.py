"""S11 / T46–T48: mock workloads, handover commands and offline clean setup."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv
from access_intake.ingest import load_document
from access_intake.providers.mock import MockProvider
from access_intake.worker import run_pending
from support import ROOT,MOCKS
from worker_support import OperationCase

class HandoverS11(OperationCase):
    def test_t46_400_and_2000_messages_with_two_operator_instances(self):
        inputs=sorted((ROOT/'tests/inputs/workload').glob('*.json'));self.assertEqual(len(inputs),2000)
        preview=MockProvider(MOCKS/'workload-manifest.json');first=load_document(inputs[0])
        response=preview.extract(first.message,source_sha256=first.source_sha256,configuration=self.settings)
        self.assertEqual(json.loads(response['output_text'])['request_id'],'LOAD-0001')
        for size in (400,2000):
            with self.subTest(messages=size):
                store=type(self.store)(self.folder/f'{size}.sqlite');started=time.monotonic()
                for path in inputs[:size]:store.register(load_document(path),self.settings)
                provider=MockProvider(MOCKS/'workload-manifest.json')
                with ThreadPoolExecutor(2) as pool:
                    futures=[pool.submit(run_pending,store,lambda config:provider,workers=2,rpm=0) for _ in range(2)]
                    for future in futures:future.result()
                rows=store.queue();self.assertEqual(len(rows),size);self.assertEqual(len(provider.calls),size)
                self.assertTrue(all(row['owner']=='System Owner' and row['error'] is None and row['extraction']['request_id']+'.json'==row['document_id'] for row in rows))
                print(f'MOCK workload={size} workers=2 operators=2 rpm=0 model=fixture-v1 elapsed_seconds={time.monotonic()-started:.3f}')
    def test_t47_readme_handover_names_supported_setup_and_commands(self):
        readme=(ROOT/'README.md').read_text()
        for required in ('Python','API_KEY','queue','resume','retry','accuracy','requirements.lock','gpt-5.4-mini','single host'):
            self.assertIn(required,readme)
        result=subprocess.run([sys.executable,str(ROOT/'tests/cli_runner.py'),'intake',str(ROOT/self.oracle['input']),'--db',str(self.db),'--provider','mock'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.store.queue()[0]['owner'],'System Owner')
    def test_t48_clean_environment_installs_only_hashed_local_wheels(self):
        lock=ROOT/'requirements.lock';self.assertTrue(lock.is_file())
        self.assertTrue(list((ROOT/'.wheelhouse').glob('*.whl')))
        environment=self.folder/'clean';venv.EnvBuilder(with_pip=False).create(environment)
        uv=shutil.which('uv');self.assertIsNotNone(uv,'Install uv or prepare a pip-enabled environment for this offline installation check')
        installed=subprocess.run([uv,'--no-cache','pip','install','--python',str(environment/'bin/python'),'--no-index','--find-links',str(ROOT/'.wheelhouse'),'--require-hashes','-r',str(lock)],capture_output=True,text=True,timeout=30)
        self.assertEqual(installed.returncode,0,installed.stderr)
        result=subprocess.run([str(environment/'bin/python'),str(ROOT/'tests/cli_runner.py'),'intake',str(ROOT/self.oracle['input']),'--db',str(self.folder/'clean.sqlite'),'--provider','mock'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
