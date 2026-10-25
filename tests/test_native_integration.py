"""Exercise the compiled, borrowed Guardian code through a local Responses SSE fixture.

These are transport/parser/enforcement tests, not claims about model judgment.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest

import test_bridge
from guardian_bridge import bridge as b

BINARY = b.ROOT/'build/debug/guardian-review'

class Fixture:
    def __init__(self):
        self.outputs=['{"outcome":"allow"}']
        self.requests=[]
        self.http_status=200
        self.delay=0
        self.completed=True
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.requests.append(body)
                time.sleep(fixture.delay)
                if fixture.http_status!=200:
                    self.send_response(fixture.http_status);self.end_headers()
                    self.wfile.write(b'{"error":{"message":"fixture unavailable","type":"invalid_request_error"}}')
                    return
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.send_header('OpenAI-Model','fixture-guardian')
                self.end_headers()
                output=fixture.outputs[min(len(fixture.requests)-1,len(fixture.outputs)-1)]
                item={'type':'message','id':'msg_1','role':'assistant','content':[{'type':'output_text','text':output}]}
                events=[{'type':'response.created','response':{'id':'resp_fixture'}},
                        {'type':'response.output_item.done','output_index':0,'item':item}]
                if fixture.completed:events.append({'type':'response.completed','response':{'id':'resp_fixture','status':'completed','output':[item]}})
                try:
                    for event in events:self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
                    self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

@unittest.skipUnless(BINARY.exists(),'build native binary first')
class NativeIntegration(test_bridge.HostTests):
    # Do not inherit the unit test cases a second time.
    def setUp(self):
        super().setUp()
        self.fixture=Fixture();self.addCleanup(self.fixture.close)
        native={'codex_home':str(self.root/'empty-codex-home'),'model':'codex-auto-review','timeout_ms':5000,
                'provider':{'name':'fixture','base_url':f'http://127.0.0.1:{self.fixture.server.server_port}',
                            'wire_api':'responses','requires_openai_auth':False,'request_max_retries':0}}
        self.config['native']=native
        self.config_path.write_text(json.dumps({k:v for k,v in self.config.items() if not k.startswith('_')}))
        self.config=b.config_load(self.config_path)

    def test_native_allow_and_no_execution(self):
        sentinel=self.root/'MUST_NOT_EXIST'
        self.payload['toolCall']['args']['CommandLine']=f'touch {sentinel}'
        result=b.review(self.payload,self.config,True)
        self.assertEqual(result['decision'],'auto_approve')
        self.assertFalse(sentinel.exists())
        request=self.fixture.requests[0]
        self.assertEqual(request['tools'],[])
        self.assertEqual(request['tool_choice'],'none')
        self.assertIn('User Authorization',request['instructions'])
        self.assertIn(str(sentinel),json.dumps(request['input']))

    def test_native_deny_blocks(self):
        self.fixture.outputs=['{"outcome":"deny","risk_level":"high","user_authorization":"unknown","rationale":"fixture denial"}']
        result=b.review(self.payload,self.config,True)
        self.assertEqual(result['decision'],'deny')
        self.assertIn('fixture denial',result['reason'])
        self.assertIn('workaround',result['reason'])

    def test_native_parser_tolerates_prose_like_upstream(self):
        self.fixture.outputs=['Here is my verdict: {"outcome":"allow"}']
        self.assertEqual(b.review(self.payload,self.config,True)['decision'],'auto_approve')

    def test_native_invalid_output_retries_then_blocks(self):
        self.fixture.outputs=['{"outcome":"approve"}']
        self.assertEqual(b.review(self.payload,self.config,True)['decision'],'deny')
        self.assertEqual(len(self.fixture.requests),3)

    def test_native_parse_retry_recovers(self):
        self.fixture.outputs=['not JSON','{"outcome":"allow"}']
        self.assertEqual(b.review(self.payload,self.config,True)['decision'],'auto_approve')
        self.assertEqual(len(self.fixture.requests),2)

    def test_native_auth_failure_never_becomes_approval(self):
        self.fixture.http_status=401
        self.assertEqual(b.review(self.payload,self.config,True)['decision'],'deny')
        self.assertEqual(len(self.fixture.requests),1)

    def test_native_timeout_blocks(self):
        self.config['native']['timeout_ms']=100
        self.config_path.write_text(json.dumps({k:v for k,v in self.config.items() if not k.startswith('_')}))
        self.config=b.config_load(self.config_path)
        self.fixture.delay=.5
        self.assertEqual(b.review(self.payload,self.config,True)['decision'],'deny')

    def test_native_incomplete_stream_blocks(self):
        self.fixture.completed=False
        self.assertEqual(b.review(self.payload,self.config,True)['decision'],'deny')

    def test_native_policy_and_role_provenance(self):
        prepared=b.review(self.payload,self.config,True,'prepare')
        self.assertEqual(prepared['schema']['properties']['outcome']['enum'],['allow','deny'])
        transcript=json.dumps(prepared['input'])
        self.assertIn('USER_EXPLICIT',transcript)
        self.assertIn('MODEL',transcript)
        self.assertIn('tool result',transcript)
        self.assertEqual(len(self.fixture.requests),0)

    def test_hook_process_fail_closed_on_malformed_input(self):
        process=subprocess.run([sys.executable,str(b.ROOT/'bridge.py'),'--config',str(self.config_path),'hook'],input=b'{',capture_output=True)
        self.assertEqual(process.returncode,0)
        self.assertEqual(json.loads(process.stdout)['decision'],'deny')
        self.assertEqual(set(json.loads(process.stdout)),{'decision','reason'})

    def test_native_oversized_complete_action_blocks_before_inference(self):
        self.payload['toolCall']['args']['CommandLine']='echo '+'x'*600_000
        with self.assertRaises(b.BridgeError):b.review(self.payload,self.config,True)
        self.assertEqual(len(self.fixture.requests),0)

# Avoid duplicate inherited tests while retaining the common fixture setup.
for name in list(test_bridge.HostTests.__dict__):
    if name.startswith('test_') and name not in NativeIntegration.__dict__:
        setattr(NativeIntegration,name,None)

if __name__=='__main__':unittest.main()
