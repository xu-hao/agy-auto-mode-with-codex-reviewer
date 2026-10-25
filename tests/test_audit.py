"""Audit decisions without executing proposals or promoting errors to policy denials."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_bridge
from guardian_bridge import audit
from guardian_bridge import bridge as b

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_bridge.HostTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.config_path=self.fixture.config_path
        self.config=self.fixture.config
        self.log=self.root/'decisions.jsonl'
        self.config['audit_path']=str(self.log)
        self.config['audit_details']=True
        self.payload=self.fixture.payload
        self.save_config()

    def save_config(self):
        self.config_path.write_text(json.dumps({k:v for k,v in self.config.items() if not k.startswith('_')}))
        self.config=b.config_load(self.config_path)

    def records(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_approval_records_exact_command_reason_and_request(self):
        with patch.object(b,'native_call',side_effect=self.fixture.allowed):
            result=b.review(self.payload,self.config,True)
        record=self.records()[0]
        self.assertEqual(result['decision'],'auto_approve')
        self.assertEqual(record['command'],self.payload['toolCall']['args']['CommandLine'])
        self.assertEqual(record['reason'],'allowed')
        self.assertEqual(record['session_id'],self.fixture.session)
        self.assertEqual(record['cwd'],str(self.root))
        self.assertEqual(record['execution_status'],'not_observed')
        self.assertTrue(record['binding'])
        self.assertEqual(stat.S_IMODE(self.log.stat().st_mode),0o600)
        self.assertFalse((self.root/'sentinel').exists())

    def test_rejection_records_rationale(self):
        def denied(c,m,r):
            result=self.fixture.allowed(c,m,r)
            result.update(decision='block',assessment={'outcome':'deny','risk_level':'high','rationale':'Not authorized'})
            return result
        with patch.object(b,'native_call',side_effect=denied):
            self.assertEqual(b.review(self.payload,self.config,True)['decision'],'deny')
        record=self.records()[0]
        self.assertEqual(record['status'],'reviewed')
        self.assertEqual(record['decision'],'block')
        self.assertEqual(record['reason'],'Not authorized')

    def test_review_failure_is_logged_separately(self):
        with patch.object(b,'native_call',side_effect=TimeoutError('Reviewer timed out')):
            with self.assertRaises(TimeoutError):b.review(self.payload,self.config,True)
        record=self.records()[0]
        self.assertEqual(record['status'],'error')
        self.assertEqual(record['decision'],'block')
        self.assertEqual(record['error_type'],'TimeoutError')
        self.assertNotIn('assessment',record)

    def test_stale_approval_is_logged_as_error_only(self):
        def stale(c,m,r):
            self.fixture.records.append({'type':'USER_INPUT','source':'USER_EXPLICIT','status':'DONE','content':'Stop.'})
            self.fixture.write_records()
            return self.fixture.allowed(c,m,r)
        with patch.object(b,'native_call',side_effect=stale):
            with self.assertRaises(b.BridgeError):b.review(self.payload,self.config,True)
        records=self.records()
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['status'],'error')
        self.assertEqual(records[0]['decision'],'block')

    def test_metadata_mode_omits_command_and_rationale(self):
        self.config['audit_details']=False;self.save_config()
        with patch.object(b,'native_call',side_effect=self.fixture.allowed):b.review(self.payload,self.config,True)
        record=self.records()[0]
        self.assertNotIn('command',record)
        self.assertNotIn('reason',record)
        self.assertEqual(record['decision'],'approve')

    def test_symlinked_audit_file_blocks_approval_without_altering_target(self):
        target=self.root/'keep';target.write_text('user data')
        self.log.symlink_to(target)
        with patch.object(b,'native_call',side_effect=self.fixture.allowed):
            with self.assertRaises(OSError):b.review(self.payload,self.config,True)
        self.assertEqual(target.read_text(),'user data')

    def test_shared_readable_log_is_rejected(self):
        self.log.write_text('');self.log.chmod(0o644)
        with patch.object(b,'native_call',side_effect=self.fixture.allowed):
            with self.assertRaises(audit.AuditError):b.review(self.payload,self.config,True)
        self.assertEqual(self.log.read_text(),'')

    def test_malformed_hook_input_is_audited_and_denied(self):
        incoming=io.TextIOWrapper(io.BytesIO(b'{'))
        out=io.StringIO()
        with patch.object(sys,'stdin',incoming),redirect_stdout(out),redirect_stderr(io.StringIO()):
            code=b.main(['--config',str(self.config_path),'hook'])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out.getvalue())['decision'],'deny')
        self.assertEqual(self.records()[0]['status'],'error')

    def test_prepare_mode_creates_no_decision_record(self):
        with patch.object(b,'native_call',return_value={'input':[]}):b.review(self.payload,self.config,True,'prepare')
        self.assertFalse(self.log.exists())

    def test_parallel_records_remain_complete(self):
        response={'status':'reviewed','decision':'approve','assessment':{'outcome':'allow','rationale':'allowed'}}
        def write(index):
            request={'request_id':str(index),'action':{'tool':'run_command','arguments':{'CommandLine':'echo '+str(index)+'x'*30_000}}}
            audit.decision(self.config,request,response)
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(write,range(16)))
        records=self.records()
        self.assertEqual(len(records),16)
        self.assertEqual({r['request_id'] for r in records},{str(i) for i in range(16)})

    def test_incomplete_record_is_not_appended_over(self):
        self.log.write_text('{incomplete');self.log.chmod(0o600)
        with self.assertRaises(audit.AuditError):audit.decision(self.config,{}, {'decision':'approve'})
        self.assertEqual(self.log.read_text(),'{incomplete')

    def test_reader_retries_partial_tail(self):
        line=audit.encoded({'status':'reviewed','decision':'approve'})+b'\n'
        self.log.write_bytes(line[:10]);self.log.chmod(0o600)
        rows=[]
        offset,identity=audit.read_log(self.log,rows.append)
        self.assertEqual(rows,[])
        with self.log.open('ab') as stream:stream.write(line[10:])
        audit.read_log(self.log,rows.append,offset,identity)
        self.assertEqual(len(rows),1)

    def test_viewer_filters_and_escapes_terminal_controls(self):
        request={'action':{'tool':'run_command','arguments':{'CommandLine':'echo \x1b[31mline\nnext'}}}
        for status,decision in [('reviewed','approve'),('reviewed','block'),('error','block')]:
            audit.decision(self.config,request,{'status':status,'decision':decision,'assessment':{'outcome':'allow' if decision=='approve' else 'deny','rationale':'reason'}})
        args=[sys.executable,str(b.ROOT/'scripts/audit.py'),'--config',str(self.config_path)]
        human=subprocess.run(args,capture_output=True,text=True,check=True).stdout
        self.assertIn('APPROVED',human);self.assertIn('REJECTED',human);self.assertIn('ERROR',human)
        self.assertNotIn('\x1b',human)
        for choice in ('approved','rejected','errors'):
            output=subprocess.run([*args,'--decision',choice,'--json'],capture_output=True,text=True,check=True).stdout
            self.assertEqual(len(output.splitlines()),1)

if __name__=='__main__':unittest.main()
