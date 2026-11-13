"""S12 / T49: actual artifact checks and explicitly simulated report history."""
import json
import subprocess
import sys
from access_intake.artifacts import export_current
from worker_support import OperationCase
from support import ROOT, MOCKS, read_json

class VerificationS12(OperationCase):
    def setUp(self):
        super().setUp()
        self.out=self.folder/'deliverables'
        revision=self.register(1)
        self.store.record_result(revision,read_json(MOCKS/'scoring-correct.json')[0])
        export_current(self.store,self.out)
        self.expected=self.folder/'expected.json'
        self.expected.write_text(json.dumps({'cases':{'O01':self.oracle}}))

    def report(self):
        from access_intake.verification import write_verification
        return write_verification(self.store,self.out/'verification.md',expected_path=self.expected,
            observations_path=MOCKS/'verification-assertions.json',test_run_path=None)

    def test_t49_report_retains_failed_and_repaired_mock_observations(self):
        result=self.report()
        self.assertTrue(result['passed'])
        self.assertEqual(result['external_pending'],['R-121','R-122','R-123'])
        text=(self.out/'verification.md').read_text()
        for phrase in ('before repair','repaired rerun','FAIL','PASS','simulated','fixture-v1','mock',
                       'Intended comparison','Operating limits','resume','retry','single host','No live'):
            self.assertIn(phrase,text)
        self.assertEqual(len(result['simulated_events']),2)
        self.assertFalse(result['simulated_events'][0]['passed'])

    def test_t49_actual_artifact_failure_stays_failed_until_repaired(self):
        queue=self.out/'queue.json';original=queue.read_bytes()
        queue.write_text('[]')
        result=self.report();self.assertFalse(result['passed'])
        self.assertIn('FAIL',(self.out/'verification.md').read_text())
        # This rerun restores the original saved mock evidence, not a measured oracle.
        queue.write_bytes(original)
        self.assertTrue(self.report()['passed'])

    def test_t49_cli_returns_failure_when_independent_expected_fact_disagrees(self):
        expected=read_json(self.expected);expected['cases']['O01']['extraction']['environment']='production'
        self.expected.write_text(json.dumps(expected))
        result=subprocess.run([sys.executable,str(ROOT/'tests/cli_runner.py'),'verify','--db',str(self.db),
            '--out',str(self.out/'verification.md'),'--expected',str(self.expected)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertTrue((self.out/'verification.md').exists())
        self.assertIn('independent source expectations',(self.out/'verification.md').read_text())
