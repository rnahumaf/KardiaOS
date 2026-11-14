import subprocess,sys,time,json
import numpy as np
import pytest
import kardiaos.qt_client as client
from kardiaos.automatic_analysis import Cancelled
REAL_INFER_QT=client.infer_qt

def test_own_qt_process_cancels_without_orphan(monkeypatch):
    original=subprocess.Popen;children=[]
    def spawn(args,**kw):
        p=original([sys.executable,'-I','-c','import sys,time;sys.stdin.buffer.read();time.sleep(20)'],**kw);children.append(p);return p
    monkeypatch.setattr(client,'runtime_config',lambda:{'python':sys.executable});monkeypatch.setattr(client.subprocess,'Popen',spawn)
    start=time.monotonic()
    # Use the original function, bypassing only the unit-suite's default subprocess substitute.
    with pytest.raises(Cancelled):REAL_INFER_QT(np.ones((3000,1)),lambda:time.monotonic()-start>.3)
    assert len(children)==1 and children[0].poll() is not None

@pytest.mark.parametrize('bad',['hash','index','nonfinite'])
def test_untrusted_worker_output_cannot_generate_qtc(monkeypatch,bad):
    response=dict(status='ok',checkpoint_sha256=client.WEIGHT_SHA256,leads=[dict(metrics={'qt':400},beats=[dict(r=300,qon=290,qoff=310,toff=410)])])
    if bad=='hash':response['checkpoint_sha256']='wrong'
    if bad=='index':response['leads'][0]['beats'][0]['toff']=3001
    if bad=='nonfinite':response['leads'][0]['metrics']['qt']=float('nan')
    original=subprocess.Popen
    payload=json.dumps(response)
    def spawn(args,**kw):return original([sys.executable,'-I','-c','import sys;sys.stdin.buffer.read();sys.stdout.write('+repr(payload)+')'],**kw)
    monkeypatch.setattr(client,'runtime_config',lambda:{'python':sys.executable});monkeypatch.setattr(client.subprocess,'Popen',spawn)
    with pytest.raises(ValueError):REAL_INFER_QT(np.ones((3000,1)))
