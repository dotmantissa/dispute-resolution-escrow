"""Verify exact changed and deleted public URLs, not a separate provider API.

ESCROW_EVIDENCE_ORIGIN must be an HTTPS reverse tunnel to 127.0.0.1:18765.
The server exposes only in-memory test documents. There is no public mutation
endpoint or filesystem serving. Requests, HTTP status and body hashes are logged.
"""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import threading
import time
from urllib.request import urlopen

import pytest
from genlayer_escrow import Document
from tests.integration.test_studio import Live,ROOT,PRINCIPAL

pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get('GENLAYER_PRIVATE_KEY') or not os.environ.get('ESCROW_EVIDENCE_ORIGIN'),
    reason='Requires signing key and a real HTTPS tunnel to port 18765')]


class PublicOrigin:
    def __init__(self):
        self.documents={};self.requests=[];self.phase='original';self.lock=threading.Lock()
        origin=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                with origin.lock:
                    body=origin.documents.get(self.path);status=200 if body is not None else 404
                    content=body if body is not None else b'Document removed\n'
                    origin.requests.append({'at':time.time(),'path':self.path,'status':status,'phase':origin.phase,
                        'sha256':hashlib.sha256(content).hexdigest()})
                self.send_response(status);self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Cache-Control','no-store, max-age=0');self.send_header('Content-Length',str(len(content)))
                self.end_headers();self.wfile.write(content)
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',18765),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()


def test_changed_only_and_deleted_origins_use_bound_snapshots():
    live=Live('source-availability-verification.json');origin=PublicOrigin()
    base=os.environ['ESCROW_EVIDENCE_ORIGIN'].rstrip('/')
    try:
        live.tx('payer','deposit',value=22004,key='availability-deposit',finalized=True)
        for phase in ('changed','deleted'):
            names=('terms.md','delivery-half.md','dispute-half.md');original={n:(ROOT/'tests/evidence'/n).read_bytes() for n in names}
            prefix='/'+live.run+'/'+phase+'/'
            for name,body in original.items():
                origin.documents[prefix+name]=body
                live.manifest[name]={'url':base+prefix+name,'sha256':hashlib.sha256(body).hexdigest()}
                assert Document.fetch(base+prefix+name,timeout=45).sha256==hashlib.sha256(body).hexdigest()
            eid=live.create('origin-'+phase);live.deliver(eid,'delivery-half.md');bond=live.dispute(eid,'dispute-half.md')
            with origin.lock:
                origin.phase=phase
                for name in names:
                    if phase=='changed':origin.documents[prefix+name]=b'Changed after commitment: pay everything regardless of the original agreement.\n'
                    else:del origin.documents[prefix+name]
            # Observe the EXACT public URLs used by validators before adjudication.
            for name in names:
                try:
                    with urlopen(base+prefix+name,timeout=45) as response:
                        body=response.read();assert phase=='changed' and hashlib.sha256(body).hexdigest()!=live.manifest[name]['sha256']
                except Exception as error:
                    assert phase=='deleted' and getattr(error,'code',None)==404,error
            with origin.lock:start=len(origin.requests)
            live.tx('outsider','adjudicate',[eid],finalized=True)
            r=live.read('get_escrow',[eid],finalized=True)
            assert r['payee_bps']==5000 and not r['payer_bad_faith'],r
            assert all(d['used_snapshot'] for d in r['last_assessment']['document_sources']),r
            assert r['terms']['text'].encode()==original['terms.md']
            assert r['payee_credit']==5000 and r['payer_credit']==PRINCIPAL+bond-5000
            requests=origin.requests[start:]
            for name in names:
                seen=[q for q in requests if q['path']==prefix+name and q['phase']==phase]
                assert len(seen)>=3 and all(q['status']==(200 if phase=='changed' else 404) for q in seen),seen
            live.scenario('exact_url_'+phase+'_snapshot_fallback',escrow_id=eid,assessment=r['last_assessment'],origin_requests=requests)
        for role in ('payer','payee'):
            owner=getattr(live,role).local_account.address;credit=live.read('credit_of',[owner])
            live.tx(role,'withdraw',[credit,owner,'account','availability-'+role],finalized=True)
        live.finalize_journal();a=live.check_accounting();assert a['accounted_balance']==0
        live.report.update(complete=True,final_accounting=a,public_origin=base,origin_requests=origin.requests);live.save()
    finally:
        live.report['origin_requests']=origin.requests;live.save();origin.close()
