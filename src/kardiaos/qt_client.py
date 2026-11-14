"""Cancelable local process for the original trained QT segmenter."""
from pathlib import Path
import io,json,os,subprocess,sys,time
import numpy as np
from .research import runtime_config

WEIGHT_SHA256='41f0b6474a9769f59ba0be099412c665b49be0ab99f9d171b5de3704c7b73cd8'

def infer_qt(raw,cancelled=lambda:False):
    from .automatic_analysis import Cancelled
    cfg=runtime_config();worker=Path(__file__).with_name('qt_worker.py')
    if getattr(sys,'frozen',False):worker=Path(sys.executable).parent/'source/src/kardiaos/qt_worker.py'
    weights=Path(__file__).parent/'assets/qt-segmenter-082.pt'
    x=np.asarray(raw,dtype=float)
    if x.ndim!=2 or x.shape[0]!=3000 or x.shape[1] not in (1,2) or not np.isfinite(x).all():raise ValueError('Janela QT incompatível.')
    if cancelled():raise Cancelled()
    data=io.BytesIO();np.savez(data,raw=x)
    env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MPLBACKEND='Agg')
    child=subprocess.Popen([cfg['python'],'-I','-B',str(worker),'--weights',str(weights)],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    began=time.monotonic();payload=data.getvalue()
    try:
        while True:
            if cancelled():raise Cancelled()
            if time.monotonic()-began>120:raise ValueError('Tempo limite na estimativa QT.')
            try:out,_=child.communicate(input=payload,timeout=.2);break
            except subprocess.TimeoutExpired:payload=None
        if child.returncode:raise ValueError('Modelo QT local indisponível ou checkpoint incompatível.')
        result=json.loads(out.decode('utf-8'))
        if result.get('status')!='ok' or result.get('checkpoint_sha256')!=WEIGHT_SHA256 or len(result.get('leads',[]))!=x.shape[1]:raise ValueError('Saída QT incompatível.')
        for lead in result['leads']:
            if not isinstance(lead.get('beats'),list) or not isinstance(lead.get('metrics'),dict):raise ValueError('Marcos QT inválidos.')
            for beat in lead['beats']:
                for key in ('r','qon','qoff','toff'):
                    if key in beat and (not isinstance(beat[key],int) or not 0<=beat[key]<3000):raise ValueError('Marco QT fora da janela.')
            for value in lead['metrics'].values():
                if value is not None and (not isinstance(value,(int,float)) or not np.isfinite(value)):raise ValueError('Métrica QT inválida.')
        return result
    finally:
        if child.poll() is None:child.kill()
        child.communicate()
