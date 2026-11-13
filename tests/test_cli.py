"""S09 / T40–T41: documented operator commands on saved responses only."""
import json
import subprocess
import sys
from pathlib import Path
from worker_support import OperationCase
from support import ROOT,MOCKS

class CLIS09(OperationCase):
    def cli(self,*arguments):
        return subprocess.run([sys.executable,str(ROOT/'tests/cli_runner.py'),*map(str,arguments)],cwd=ROOT,text=True,capture_output=True,timeout=15)
    def test_t40_intake_inspection_history_resume_and_explicit_retry(self):
        result=self.cli('intake',ROOT/'materials/requests/IT-001.json','--db',self.db,'--provider','mock','--mock-manifest',MOCKS/'s04-manifest.json')
        self.assertEqual(result.returncode,0,result.stderr)
        queue=self.cli('queue','--db',self.db);self.assertEqual(queue.returncode,0,queue.stderr)
        self.assertEqual(json.loads(queue.stdout)[0]['owner'],'System Owner')
        show=self.cli('show','IT-001.json','--db',self.db);record=json.loads(show.stdout)
        self.assertEqual(record['extraction']['manager'],self.oracle['extraction']['manager'])
        self.assertEqual(self.cli('resume','--db',self.db).returncode,0)
        retry=self.cli('retry','--db',self.db,'--document-id','IT-001.json','--attempt-id',record['attempt_id'],'--force')
        self.assertEqual(retry.returncode,0,retry.stderr)
        self.assertEqual(len(json.loads(self.cli('history','IT-001.json','--db',self.db).stdout)),2)
    def test_t41_invalid_export_is_visible_while_valid_input_completes(self):
        result=self.cli('intake',ROOT/'tests/inputs/invalid/invalid-json.json',ROOT/'materials/requests/IT-001.json','--db',self.db,'--provider','mock','--mock-manifest',MOCKS/'s04-manifest.json')
        self.assertNotEqual(result.returncode,0)
        queue={r['document_id']:r for r in json.loads(self.cli('queue','--db',self.db).stdout)}
        self.assertEqual(queue['IT-001.json']['owner'],'System Owner')
        self.assertEqual(queue['invalid-json.json']['status'],'error');self.assertIsNone(queue['invalid-json.json']['extraction'])
    def test_t41_duplicate_basenames_are_rejected_without_overwriting(self):
        one=self.folder/'a'/'IT-001.json';two=self.folder/'b'/'IT-001.json'
        one.parent.mkdir();two.parent.mkdir();raw=(ROOT/self.oracle['input']).read_bytes();one.write_bytes(raw);two.write_bytes(raw)
        result=self.cli('intake',one,two,'--db',self.db,'--provider','mock')
        self.assertNotEqual(result.returncode,0);self.assertIn('duplicate',result.stderr.lower())
        self.assertEqual(json.loads(self.cli('queue','--db',self.db).stdout),[])
