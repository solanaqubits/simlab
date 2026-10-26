"""Runner boundaries and independent analytic numerical expectations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from simlab_quantum.protocol import SCHEMA, LIMITS, read_json, sha, implementation_hash, validate_request
from simlab_quantum.runner import run_request, audit_archive, execute


def request(ops=None, n=2, mode='statevector', shots=32):
    return {'schema': SCHEMA, 'circuit': {'n_qubits': n, 'operations': ops or []},
            'config': {'mode': mode, 'shots': shots, 'seed': 42}}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = 0

    def run_case(self, obj, python=sys.executable):
        self.index += 1
        src = self.root/f'input{self.index}.json'
        src.write_bytes(obj if isinstance(obj, bytes) else json.dumps(obj).encode())
        dest = self.root/f'run{self.index}'
        r = run_request(src, dest, python)
        return r, dest

    def test_bell_both_modes_and_archive(self):
        import numpy as np
        for mode in ['statevector', 'density_matrix']:
            r, d = self.run_case(request([{'gate':'H','targets':[0]}, {'gate':'CX','targets':[0,1]}], mode=mode))
            self.assertEqual(r['status'], 'COMPLETED', r)
            self.assertEqual(r['evidence_kind'], 'numerical_simulation')
            psi = np.array([1,0,0,1])/np.sqrt(2)
            np.testing.assert_allclose(np.load(d/'state.npy', allow_pickle=False), psi if mode=='statevector' else np.outer(psi,psi), atol=1e-12)
            result = read_json((d/'result.json').read_bytes())['result']
            self.assertEqual(sum(result['counts'].values()), 32)
            self.assertEqual(result['diagnostics']['state_scope'], 'final_state')
            self.assertEqual(audit_archive(d, r['request_sha256'], implementation_hash())['status'], 'ARCHIVE_CONSISTENT')

    def test_bit_order(self):
        import numpy as np
        r,d=self.run_case(request([{'gate':'X','targets':[0]}]))
        self.assertEqual(r['status'],'COMPLETED')
        np.testing.assert_array_equal(np.load(d/'state.npy'), [0,0,1,0])

    def test_amplitude_damping_analytic(self):
        import numpy as np
        r,d=self.run_case(request([{'gate':'X','targets':[0]}, {'gate':'AMPLITUDE_DAMPING','targets':[0],'probability':.3}], n=1, mode='density_matrix'))
        self.assertEqual(r['status'],'COMPLETED')
        np.testing.assert_allclose(np.load(d/'state.npy'), np.diag([.3,.7]), atol=1e-12)

    def test_dynamic_first_trajectory(self):
        r,d=self.run_case({**request([{'gate':'H','targets':[0]}, {'gate':'MEASURE','targets':[0],'clbits':[0]}],n=1),
                          'circuit':{'n_qubits':1,'n_clbits':1,'operations':[{'gate':'H','targets':[0]}, {'gate':'MEASURE','targets':[0],'clbits':[0]}]}})
        self.assertEqual(r['status'],'COMPLETED')
        q=read_json((d/'result.json').read_bytes())['result']
        self.assertEqual(q['diagnostics']['state_scope'],'first_trajectory')
        self.assertEqual(sum(q['classical_counts'].values()),32)
        self.assertEqual(len(q['probabilities']),1)

    def test_seed_reproducible(self):
        obj=request([{'gate':'H','targets':[0]}])
        a,da=self.run_case(obj);b,db=self.run_case(obj)
        self.assertEqual(a['status'],b['status'])
        self.assertEqual((da/'state.npy').read_bytes(), (db/'state.npy').read_bytes())
        self.assertEqual(read_json((da/'result.json').read_bytes())['result']['counts'],read_json((db/'result.json').read_bytes())['result']['counts'])

    def test_duplicate_nonfinite_malformed_input(self):
        for data in [b'{"schema":1,"schema":2}', b'NaN', b'{', b'1e999', b'\xff', '{}'.encode('utf-16')]:
            with self.subTest(data=data):
                r,_=self.run_case(data);self.assertEqual(r['status'],'INVALID_INPUT',r)

    def test_unknown_fields_and_invalid_indices(self):
        for obj in [{**request(), 'extra':1},request([{'gate':'H','targets':[2]}]),request([{'gate':'XY','targets':[0]}])]:
            r,_=self.run_case(obj);self.assertEqual(r['status'],'INVALID_INPUT',r)

    def test_memory_policy_refusal(self):
        for obj in [request(n=17),request(n=9,mode='density_matrix')]:
            r,_=self.run_case(obj);self.assertEqual(r['status'],'RESOURCE_LIMIT',r)

    def test_work_policy_refusal(self):
        obj=request([{'gate':'RESET','targets':[0]}]*512,n=16,shots=4096)
        r,_=self.run_case(obj);self.assertEqual(r['status'],'RESOURCE_LIMIT')

    def test_shots_bool_and_config_override(self):
        for config in [{'shots':True},{'memory_gib':100},{'timeout_seconds':300},{'shots':4097}]:
            obj=request();obj['config'].update(config)
            r,_=self.run_case(obj);self.assertEqual(r['status'],'INVALID_INPUT')

    def test_invalid_unitary_and_noise_mode(self):
        for obj in [request([{'gate':'UNITARY','targets':[0],'matrix':[[[1,0],[1,0]],[[0,0],[1,0]]]}]),
                    request([{'gate':'BIT_FLIP','targets':[0],'probability':.5}])]:
            r,_=self.run_case(obj);self.assertEqual(r['status'],'INVALID_INPUT')

    def test_input_size_refusal(self):
        r,d=self.run_case(b' '*(LIMITS['max_input_bytes']+1))
        self.assertEqual(r['status'],'INVALID_INPUT');self.assertFalse((d/'request.json').exists())

    def test_existing_directory_never_overwritten(self):
        r,d=self.run_case(request());before=(d/'receipt.json').read_bytes()
        with self.assertRaises(FileExistsError):run_request(d/'request.json', d)
        self.assertEqual((d/'receipt.json').read_bytes(),before)

    def test_missing_input_receipt(self):
        r=run_request(self.root/'absent', self.root/'failure')
        self.assertEqual(r['status'],'IO_ERROR')
        self.assertTrue((self.root/'failure/receipt.json').is_file())

    def test_missing_interpreter(self):
        r,_=self.run_case(request(), '/nonexistent/python')
        self.assertEqual(r['status'],'IO_ERROR')

    def test_missing_dependencies(self):
        # A fresh venv without site packages, not a mock ImportError.
        subprocess.run([sys.executable,'-m','venv','--without-pip',str(self.root/'bare')],check=True)
        r,_=self.run_case(request(),str(self.root/'bare/bin/python'))
        self.assertEqual(r['status'],'DEPENDENCY_ERROR',r)

    def test_real_host_timeout(self):
        d=self.root/'timeout';d.mkdir()
        rc,timed=execute([sys.executable,'-I','-c','import time; time.sleep(30)'],d,dict(os.environ),.15)
        self.assertTrue(timed);self.assertEqual(rc,-9)

    def test_timeout_classification(self):
        with patch('simlab_quantum.runner.execute',return_value=(-9,True)):
            r,_=self.run_case(request())
        self.assertEqual(r['status'],'EXEC_TIMEOUT')

    def test_signal_not_oom(self):
        with patch('simlab_quantum.runner.execute',return_value=(-9,False)):
            r,_=self.run_case(request())
        self.assertEqual(r['status'],'EXEC_ERROR');self.assertNotIn('OOM',r['status'])

    def test_bad_worker_protocol(self):
        def broken(command,d,env,timeout):
            (d/'stdout.log').write_text('{"status":"COMPLETED"}')
            return 0,False
        with patch('simlab_quantum.runner.execute',side_effect=broken):r,_=self.run_case(request())
        self.assertEqual(r['status'],'EXEC_ERROR')

    def test_snapshot_mutation(self):
        def change(command,d,env,timeout):
            (d/'request.json').chmod(0o600);(d/'request.json').write_text('{}')
            return -9,False
        with patch('simlab_quantum.runner.execute',side_effect=change):r,_=self.run_case(request())
        self.assertEqual(r['status'],'INTEGRITY_ERROR')

    def test_archive_tamper_and_external_pins(self):
        r,d=self.run_case(request())
        with self.assertRaises(ValueError):audit_archive(d,'0'*64,implementation_hash())
        with self.assertRaises(ValueError):audit_archive(d,r['request_sha256'],'0'*64)
        (d/'state.npy').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):audit_archive(d,r['request_sha256'],implementation_hash())

    def test_archive_rehashed_result_still_checks_request(self):
        r,d=self.run_case(request())
        p=d/'result.json';j=read_json(p.read_bytes());j['result']['config']['shots']=123
        p.write_text(json.dumps(j));r['artifacts']['result.json']=sha(p.read_bytes())
        (d/'receipt.json').write_text(json.dumps(r))
        with self.assertRaises(ValueError):audit_archive(d,r['request_sha256'],implementation_hash())

    def test_implementation_change(self):
        from simlab_quantum.protocol import implementation_manifest
        original=implementation_manifest()
        with patch('simlab_quantum.runner.implementation_manifest',side_effect=[original,{}]):
            r,_=self.run_case(request())
        self.assertEqual(r['status'],'INTEGRITY_ERROR')

    def test_optional_import_and_help_without_dependencies(self):
        project=str(Path(__file__).resolve().parents[1])
        script='import sys;sys.path.insert(0,'+repr(project)+');import simlab_quantum.runner;assert "numpy" not in sys.modules;from simlab_quantum.__main__ import main;main()'
        p=subprocess.run([sys.executable,'-S','-c',script,'--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('Optional bounded',p.stdout)

    def test_numerical_check_failure(self):
        import numpy as np
        from simlab_quantum.worker import numerical_checks
        with self.assertRaises(ArithmeticError):numerical_checks(None,np.array([2.,0.]))
        with self.assertRaises(ArithmeticError):numerical_checks(None,np.diag([2.,-1.]))
        with self.assertRaises(ArithmeticError):numerical_checks(None,np.array([float('nan')]))

if __name__=='__main__':unittest.main()
