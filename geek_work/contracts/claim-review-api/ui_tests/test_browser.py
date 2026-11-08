"""Real headless Chrome acceptance. Browser faults are injected only by this test runner.

Requires Linux google-chrome and the development Python websocket-client package.
Does not add runtime dependencies to the server or UI. Never logs session tokens.
"""
import base64
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

import websocket
BRAIN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BRAIN/'tools'))
import geek_work_claim_api_server as s


class Browser:
    def __init__(self, root):
        self.process = subprocess.Popen(['google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+str(root),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+15
        while not (root/'DevToolsActivePort').exists():
            if time.monotonic()>deadline:raise RuntimeError('chrome_start_failed')
            time.sleep(.05)
        port=int((root/'DevToolsActivePort').read_text().splitlines()[0])
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/json/list') as reply:pages=json.load(reply)
        page=next(x for x in pages if x['type']=='page')
        self.ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=15,suppress_origin=True)
        self.seq=0
        self.call('Page.enable')
        self.call('Runtime.enable')
        self.call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))

    def call(self, method, params=None):
        self.seq+=1;seq=self.seq
        self.ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
        while True:
            response=json.loads(self.ws.recv())
            if response.get('id')==seq:
                if 'error' in response:raise AssertionError('CDP command failed: '+method)
                return response.get('result',{})

    def eval(self, expression):
        value=self.call('Runtime.evaluate',dict(expression=expression,awaitPromise=True,returnByValue=True))
        if 'exceptionDetails' in value:
            detail=value['exceptionDetails'].get('exception',{}).get('description','browser_script_failed')
            raise AssertionError(detail)
        return value['result'].get('value')

    def wait(self, expression, timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.eval(expression):return
            time.sleep(.05)
        raise AssertionError('browser_wait_timeout: '+str(self.eval("document.querySelector('#message')?.textContent")))

    def click(self, selector):
        self.eval('document.querySelector('+json.dumps(selector)+').click()')

    def input(self, selector, value, event='input'):
        self.eval('(()=>{const e=document.querySelector('+json.dumps(selector)+');e.value='+json.dumps(value)+';e.dispatchEvent(new Event('+json.dumps(event)+',{bubbles:true}));})()')

    def upload(self, path):
        doc=self.call('DOM.getDocument')['root']['nodeId']
        nid=self.call('DOM.querySelector',dict(nodeId=doc,selector='#record-file'))['nodeId']
        self.call('DOM.setFileInputFiles',dict(nodeId=nid,files=[str(path)]))

    def close(self):
        self.ws.close()
        # Chrome children may outlive its launcher and still write the profile.
        # This isolated process group belongs only to this test's browser.
        try:os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:pass
        try:self.process.wait(5)
        except subprocess.TimeoutExpired:pass
        try:os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:pass
        self.process.wait(5)


class BlockingRunner(s.Runner):
    def __init__(self):
        super().__init__();self.entered=threading.Event();self.release=threading.Event()
    def run(self,path,kind):
        self.entered.set()
        if not self.release.wait(10):raise s.JobError('timeout')
        return super().run(path,kind)


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='claim-review-browser-')
        self.root=Path(self.tmp.name);self.addCleanup(self.tmp.cleanup)
        self.browser=Browser(self.root/'chrome');self.addCleanup(self.browser.close)
        self.context=None;self.server=None
        self.addCleanup(self.stop_server)

    def stop_server(self):
        if self.context and isinstance(self.context.runner,BlockingRunner):self.context.runner.release.set()
        if self.context and self.context.worker:self.context.worker.join(8)
        if self.server:self.server.shutdown();self.server.server_close()

    def start(self, mode='ready', connect=True):
        if mode=='ready':
            fixture=self.root/'fixture';shutil.copytree(BRAIN/'examples/claim-adapter-ready',fixture)
            pins=json.loads((fixture/'pins.json').read_bytes())
            src=fixture/'source.txt';ledger=fixture/'expectations.json';bundle=fixture/'source-bundle';self.record=fixture/'record.json'
        else:
            fixture=BRAIN/'examples/claim-extraction-orbit';pins=json.loads((fixture/'pins.json').read_bytes())
            bundle=BRAIN/'examples/claim-transport-orbit/source-bundle';src=bundle/'material-lean-source.txt';ledger=fixture/'expectations.json';self.record=fixture/'orbit-needs-context.json'
            pins.update(claim_map_bundle_sha256='022bbbc4659daa6cb249aed9bdb8dc8a90c85f7fb9bd828ab53964458398281b',source_claim_id='subcritical-orbit-limit',source_revision=1)
        self.source=src
        self.context=s.Context(src,pins['source_sha256'],ledger,pins['expectations_sha256'],bundle,pins['claim_map_bundle_sha256'],pins['source_claim_id'],pins['source_revision'],self.root/'session')
        self.server=s.Server(self.context);threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True).start()
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])
        self.browser.call('Page.navigate',dict(url=self.url))
        self.browser.wait("document.querySelector('#connect') && document.querySelectorAll('[data-assurance]').length===4")
        if connect:self.connect()

    def connect(self):
        self.browser.input('#context-id',self.context.id)
        self.browser.input('#token',self.context.token)
        self.browser.click('#connect')
        self.browser.wait("!document.querySelector('#workspace').hidden")
        self.browser.upload(self.record)
        self.browser.wait("document.querySelectorAll('.atom').length>0")

    def save(self):
        self.browser.click('#save');self.browser.wait("!document.querySelector('#check').disabled")

    def status(self,key):
        return self.browser.eval('document.querySelector(\'[data-status="'+key+'"]\').textContent')

    def test_ui_ready_fixture_pass(self):
        self.start();self.save();self.browser.click('#check')
        self.browser.wait("document.querySelector('[data-status=extraction]').textContent==='record_consistent'")
        self.browser.click('#build')
        self.browser.wait("document.querySelector('[data-status=adapter]').textContent==='built'")
        self.assertEqual(self.status('transport'),'contract_preserved')
        self.browser.wait("document.querySelector('#artifacts').textContent.includes('plan.json')")
        self.assertEqual(self.browser.eval("document.querySelector('#token').value"),'')
        self.assertEqual(self.browser.eval('localStorage.length+sessionStorage.length'),0)
        self.assertTrue(all(x['state']=='completed' for x in self.context.jobs.values()))
        output=os.environ.get('CLAIM_UI_EVIDENCE')
        if output:
            self.browser.eval("document.querySelector('.mapping').scrollIntoView()")
            png=self.browser.call('Page.captureScreenshot',dict(format='png'))['data']
            (Path(output)/('ready-browser-'+str(time.time_ns())+'.png')).write_bytes(base64.b64decode(png))

    def test_ui_orbit_blocked_render(self):
        self.start('orbit')
        self.assertTrue(self.browser.eval("document.querySelector('#editorial [value=ready_for_transport]').disabled"))
        self.assertIn('unresolved_questions_not_empty',self.browser.eval("document.querySelector('#gate').textContent"))
        self.save();self.browser.click('#check')
        self.browser.wait("document.querySelector('[data-status=extraction]').textContent==='needs_context'")
        self.browser.click('#build')
        self.browser.wait("document.querySelector('[data-status=adapter]').textContent==='build_blocked'")
        self.assertFalse(any(x['package_available'] for x in self.context.jobs.values()))
        self.assertEqual(self.browser.eval("document.querySelectorAll('#artifacts button').length"),0)

    def test_ui_unicode_surrogate_spans(self):
        self.start()
        result=self.browser.eval("""(async()=>{const c=await import('/ui/core.js');const p=document.querySelector('#source');const s=p.textContent;const i=s.indexOf('😀');const j=i>=0?i:[...s].find(x=>x.codePointAt(0)>65535);const start=i>=0?i:s.indexOf(j);if(start<0)throw Error('no_astral_fixture');const r=document.createRange();r.setStart(p.firstChild,start);r.setEnd(p.firstChild,start+2);const sel=getSelection();sel.removeAllRanges();sel.addRange(r);const valid=c.selectionSpan(p,s);let rejected=false;try{c.cpOffset(s,start+1)}catch(e){rejected=e.message==='surrogate_boundary_rejected'}return {valid,rejected};})()""")
        q=result['valid'];raw=self.source.read_bytes().decode('utf-8')
        self.assertEqual(raw[q['start_char']:q['end_char']],q['quote'])
        self.assertTrue(result['rejected'])
        self.browser.input('#new-role','premise_atoms','change')
        before=self.browser.eval("document.querySelectorAll('.atom').length")
        self.browser.click('#add-atom')
        self.browser.wait('document.querySelectorAll(".atom").length==='+str(before+1))

    def test_ui_combining_marks_crlf(self):
        self.start()
        source=self.source.read_bytes();self.assertIn(b'\r\n',source)
        self.assertEqual(self.browser.eval("document.querySelector('#source').textContent"),source.decode('utf-8'))
        self.browser.click('.atom button')
        self.assertEqual(self.browser.eval("document.querySelector('#source').textContent"),source.decode('utf-8'))
        self.save()
        saved=next(iter(self.context.drafts.values()))[0].read_bytes()
        self.assertEqual(saved,self.record.read_bytes())
        result=self.browser.eval("""(async()=>{const c=await import('/ui/core.js');const text='שָׁלוֹם\\r\\n😀';const p=document.createElement('pre');p.textContent=text;document.body.append(p);const r=document.createRange();r.selectNodeContents(p);const sel=getSelection();sel.removeAllRanges();sel.addRange(r);const q=c.selectionSpan(p,text);const digest=await c.sha(c.bytes(p.textContent));p.remove();return {q,digest};})()""")
        import hashlib
        self.assertEqual(result['q']['quote'],'שָׁלוֹם\r\n😀')
        self.assertEqual(result['q']['end_char'],len('שָׁלוֹם\r\n😀'))
        self.assertEqual(result['digest'],hashlib.sha256('שָׁלוֹם\r\n😀'.encode()).hexdigest())

    def test_ui_source_tamper_lock(self):
        self.start();self.save();self.source.write_bytes(b'tampered')
        self.browser.click('#refresh')
        self.browser.wait("document.querySelector('#anchors .bad')!==null")
        self.assertTrue(self.browser.eval("document.querySelector('#build').disabled"))
        self.assertFalse(self.browser.eval("document.querySelector('#save').disabled"))

    def test_ui_stale_invalidation(self):
        self.start();self.save();self.browser.click('#check')
        self.browser.wait("document.querySelector('[data-status=extraction]').textContent==='record_consistent'")
        self.browser.input('#quantities input','101') # first editable quantity = exact literal
        self.browser.wait("document.querySelector('[data-status=freshness]').textContent==='stale'")
        self.assertTrue(self.browser.eval("document.querySelector('#build').disabled"))

    def test_ui_late_response_is_historical(self):
        self.start();self.context.runner=BlockingRunner();self.save();self.browser.click('#check')
        self.assertTrue(self.context.runner.entered.wait(5))
        self.browser.input('#quantities input','101')
        self.context.runner.release.set()
        self.browser.wait("document.querySelector('#message').textContent.startsWith('historical:')")
        self.assertEqual(self.status('extraction'),'not_run')
        self.assertIn('historical',self.browser.eval("document.querySelector('#history').textContent"))

    def test_ui_missing_atom_highlight(self):
        self.start()
        before=self.browser.eval("document.querySelector('#coverage select').value")
        self.browser.input('#coverage select:nth-of-type(1)','condition_present','change')
        # Finding is the second select in the first coverage row; no observation inference.
        self.browser.eval("(()=>{const s=document.querySelectorAll('.coverage-row')[0].querySelectorAll('select')[1];s.value='missing_extracted_atom';s.dispatchEvent(new Event('change',{bubbles:true}));})()")
        self.browser.wait("document.querySelector('.finding')?.textContent==='missing_extracted_atom'")
        self.assertEqual(self.browser.eval("document.querySelector('#coverage select').value"),before)

    def test_ui_adapter_error_details(self):
        self.start('orbit');self.save();self.browser.click('#build')
        self.browser.wait("document.querySelector('[data-status=adapter]').textContent==='build_blocked'")
        self.assertIn('extraction_not_record_consistent',self.browser.eval("document.querySelector('#message').textContent"))

    def test_ui_full_status_matrix(self):
        self.start()
        result=self.browser.eval("""(async()=>{const c=await import('/ui/core.js');const host=document.createElement('div');document.body.append(host);let count=0;for(const state of c.STATES.evidence){c.renderStatuses(host,{editorial_state:'draft',reported_evidence_state:state},null,'not_run');if(host.querySelector('[data-status=evidence]').textContent!==state)throw Error('evidence');count++;}for(const name of ['extraction','adapter','transport'])for(const state of c.STATES[name]){c.renderStatuses(host,{editorial_state:'needs_context',reported_evidence_state:'source_only'},{reports:[{validator:name,status:state}]},'current');if(host.querySelector('[data-status='+name+']').textContent!==state)throw Error('status');count++;}c.renderStatuses(host,null,null,'not_run');if(host.querySelector('[data-status=transport]').textContent!=='not_run')throw Error('not_run');host.remove();return count;})()""")
        self.assertEqual(result,16)

    def test_ui_pending_edits_are_preserved(self):
        self.start()
        a='textarea[data-editor="non_claims"]';b='textarea[data-editor="open_obligations"]'
        self.browser.input(a,'["edited nonclaim"]')
        self.browser.input(b,'["edited obligation"]')
        self.browser.eval("[...document.querySelectorAll('#editors button')].find(x=>x.textContent==='Применить non_claims').click()")
        self.assertEqual(self.browser.eval('document.querySelector('+json.dumps(b)+').value'),'["edited obligation"]')
        self.assertTrue(self.browser.eval("document.querySelector('#save').disabled"))
        self.browser.eval("[...document.querySelectorAll('#editors button')].find(x=>x.textContent==='Применить open_obligations').click()")
        self.browser.wait("!document.querySelector('#save').disabled")
        self.save()
        value=json.loads(next(iter(self.context.drafts.values()))[0].read_bytes())
        self.assertEqual(value['contract']['non_claims'],['edited nonclaim'])
        self.assertEqual(value['contract']['open_obligations'],['edited obligation'])

    def test_ui_changed_span_gets_new_id(self):
        self.start()
        original=self.browser.eval("document.querySelector('.atom-id').textContent")
        self.browser.input('.bounds input','49')
        self.browser.click('.bounds button')
        self.browser.wait('document.querySelector(".atom-id").textContent!=='+json.dumps(original))
        self.assertTrue(self.browser.eval("document.querySelector('.atom-id').textContent.startsWith('atom-')"))
        self.save()
        value=json.loads(next(iter(self.context.drafts.values()))[0].read_bytes())
        atom=value['contract']['premise_atoms'][0]
        import hashlib
        self.assertEqual(atom['text_sha256'],hashlib.sha256(atom['text_raw'].encode()).hexdigest())
        self.assertIn(original,value['coverage_checks'][0]['extracted_atom_ids'])

    def test_ui_journal_download_has_no_token(self):
        self.start();self.save()
        folder=self.root/'downloads';folder.mkdir()
        self.browser.call('Browser.setDownloadBehavior',dict(behavior='allow',downloadPath=str(folder)))
        self.browser.click('#download-history')
        deadline=time.monotonic()+5
        while not list(folder.glob('claim-review-journal-*.json')):
            if time.monotonic()>deadline:self.fail('download_timeout')
            time.sleep(.05)
        raw=next(folder.glob('*.json')).read_bytes()
        journal=json.loads(raw)
        self.assertEqual(journal['schema'],'claim-review-editor-journal-1')
        self.assertNotIn(self.context.token.encode(),raw)
        self.assertTrue(all(journal[f] is False for f in s.FLAGS))
        self.assertTrue(any(row['event']=='draft_saved' for row in journal['entries']))

    def test_ui_strict_json_refuses_lossy_inputs(self):
        self.start()
        result=self.browser.eval("""(async()=>{const c=await import('/ui/core.js');const bad=['{"x":1.2}','{"x":9007199254740993}','{"x":1,"x":2}','{"x":NaN}',String.fromCharCode(0xfeff)+'{}','{"x":"'+String.fromCharCode(0xd800)+'"}'];return bad.map(s=>{try{c.strictJSON(s);return false}catch(e){return true}});})()""")
        self.assertTrue(all(result))

    def test_ui_false_assurances(self):
        self.start(connect=False)
        self.browser.eval("""(()=>{const original=window.fetch;window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0])==='/v1/context'){const b=await r.json();b.assurances.kernel_replayed=true;return new Response(JSON.stringify(b),{status:r.status,headers:r.headers});}return r;};})()""")
        self.browser.input('#context-id',self.context.id);self.browser.input('#token',self.context.token);self.browser.click('#connect')
        self.browser.wait("document.querySelector('#message').textContent==='assurance_contract_violation'")
        self.assertTrue(self.browser.eval("document.querySelector('#build').disabled"))
        self.assertEqual(self.browser.eval("[...document.querySelectorAll('[data-assurance]')].every(x=>x.textContent.endsWith('= false')&&!x.isContentEditable)"),True)


if __name__=='__main__':unittest.main()
