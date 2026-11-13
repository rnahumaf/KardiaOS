"""Local exploratory scenarios, separate from the unchanged referenced-analysis gate."""
from pathlib import Path
import io,json,os,subprocess,sys,time
import numpy as np
from .research import catalog,calibration_valid,inspect_window,runtime_config
from .measurements import measure_recording,technical_quality
from .signal import six_leads


class Cancelled(Exception): pass


def worker_scores(key,values,cancelled=lambda:False):
    cfg=runtime_config();spec=catalog()['models'][key]
    worker=Path(__file__).with_name('research_worker.py')
    if getattr(sys,'frozen',False): worker=Path(sys.executable).parent/'source/src/kardiaos/research_worker.py'
    payload=io.BytesIO();np.savez(payload,values_mv=values,model_key=np.array(key))
    env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',MPLBACKEND='Agg')
    process=subprocess.Popen([cfg['python'],'-I',str(worker),'--models',cfg['models_dir']],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    began=time.monotonic();data=payload.getvalue()
    try:
        while True:
            if cancelled(): raise Cancelled()
            if time.monotonic()-began>180: raise ValueError('Tempo limite do processo local excedido.')
            try:
                stdout,_=process.communicate(input=data,timeout=.2);break
            except subprocess.TimeoutExpired: data=None
        if process.returncode: raise ValueError('Processo local não concluiu a inferência.')
        response=json.loads(stdout.decode('utf-8'))
        if response.get('status')!='ok': raise ValueError(response.get('reason','Modelo indisponível.'))
        scores=np.asarray(response.get('scores'),dtype=float)
        if (scores.shape!=(len(spec['labels']),) or not np.isfinite(scores).all()
            or np.any((scores<0)|(scores>1)) or response.get('checkpoint_sha256')!=spec['sha256']):
            raise ValueError('Saída ou identidade do checkpoint incompatível.')
        response['scores']=[dict(label,score=float(v)) for label,v in zip(spec['labels'],scores)]
        return response
    finally:
        if process.poll() is None: process.kill()
        process.communicate()


def first_window(recording,key,cancelled=lambda:False):
    if recording is None or not recording.n or recording.meta.get('start') is None: return None,'Sem captura estabilizada.'
    length=min(recording.last_time,float(recording.meta.get('end') or recording.last_time))-float(recording.meta['start'])+1/300
    last_reason='Sem 10 s contínuos com as derivações necessárias.'
    first=int(np.searchsorted(recording.times[:recording.n],recording.meta['start']))
    offsets=(recording.times[first:recording.n:300]-recording.meta['start']).tolist()
    for offset in offsets:
        if cancelled(): raise Cancelled()
        check=inspect_window(recording,key,float(offset),require_calibration=False)
        if check['status']!='ready':
            last_reason=' '.join(check['reasons']);continue
        count=1 if key=='ecgfounder_1l' else 2
        error=technical_quality(recording.raw[check['first_sample']:check['last_sample'],:count])
        if error: last_reason=error;continue
        return check,None
    return None,last_reason


def automatic_analysis(recording,emit=lambda item:None,cancelled=lambda:False,infer=worker_scores):
    result=dict(status='running',calibration_verified=bool(recording and calibration_valid(recording)),
        clinical_validation=False,measurements=measure_recording(recording),scenarios=[],unavailable=[],
        interpretation='Hipóteses de redes, não diagnósticos nem probabilidades. Escala/orientação não são inferidas dos escores. Sem escolher cenário favorável.')
    emit(dict(kind='measurements',value=result['measurements']))
    try:
        for key,spec in catalog()['models'].items():
            if cancelled(): raise Cancelled()
            check,reason=first_window(recording,key,cancelled)
            if check is None:
                item=dict(model=key,reason=reason);result['unavailable'].append(item);emit(dict(kind='unavailable',value=item));continue
            # No anatomical orientation inferred from appearance or earlier user statements.
            signs=[(1,)] if key=='ecgfounder_1l' else [(1,1)]
            if not result['calibration_verified']:
                signs=[(1,),(-1,)] if key=='ecgfounder_1l' else [(1,1),(1,-1),(-1,1),(-1,-1)]
            for sign in signs:
                if cancelled(): raise Cancelled()
                name='I'+('+' if sign[0]>0 else '-')
                if len(sign)==2:name+=' II'+('+' if sign[1]>0 else '-')
                item=dict(model=key,name=spec['name'],leads=spec['leads'],hypothesis=name,
                    offset_seconds=check['offset_seconds'],duration_seconds=10,calibration_verified=result['calibration_verified'],
                    status='synthetic' if recording.meta.get('synthetic') else 'unvalidated_experiment',scores=[])
                emit(dict(kind='progress',value=spec['name']+' · '+name))
                raw=recording.raw[check['first_sample']:check['last_sample'],:len(sign)].astype(float)*np.array(sign)
                if key=='deeppsp_6l': raw=six_leads(raw)
                values=raw.T*recording.meta['mv_per_count']
                try:
                    response=infer(key,values,cancelled)
                    item.update(scores=response['scores'],checkpoint_sha256=response['checkpoint_sha256'],
                        preprocessing=response['preprocessing'],runtime=response['runtime'])
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    item.update(status='unavailable',reason=str(exc))
                result['scenarios'].append(item);emit(dict(kind='scenario',value=item))
        result['status']='completed'
    except Cancelled: result['status']='cancelled'
    return result


def analysis_key(recording):
    """Cache only the exact signal, timebase, contact and metadata; never persist it."""
    import hashlib
    digest=hashlib.sha256(json.dumps(recording.meta,sort_keys=True).encode())
    for values in (recording.raw,recording.times,recording.quality,recording.lead_modes):
        digest.update(values[:recording.n].tobytes())
    return digest.hexdigest()
