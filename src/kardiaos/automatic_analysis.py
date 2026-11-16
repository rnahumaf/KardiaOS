"""Local exploratory scenarios, separate from the unchanged referenced-analysis gate."""
from pathlib import Path
import io,json,os,subprocess,sys,time
import numpy as np
from .research import catalog,inspect_window,runtime_config
from .measurements import measure_recording,technical_quality
from .signal import six_leads
from .orientation import evidence_state,normal_signs,model_channels
from .processing import empirical,profile_info,model_values,scope
from . import __version__


class Cancelled(Exception): pass


def worker_scores(key,values,cancelled=lambda:False):
    cfg=runtime_config();spec=catalog()['models'][key]
    worker=Path(__file__).with_name('research_worker.py')
    if getattr(sys,'frozen',False): worker=Path(sys.executable).parent/'source/src/kardiaos/research_worker.py'
    payload=io.BytesIO();np.savez(payload,values_mv=values,model_key=np.array(key))
    env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',MPLBACKEND='Agg')
    process=subprocess.Popen([cfg['python'],'-I','-B',str(worker),'--models',cfg['models_dir']],
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


def first_window(recording,key,cancelled=lambda:False, *, offset=0., duration=None, exact=False):
    request=scope(recording,offset,duration)
    if recording is None or request['duration_seconds'] < 10-1e-6:
        return None,'Sao necessarios 10 s continuos no trecho escolhido.'
    last_reason='Sem 10 s continuos com as derivacoes necessarias.'
    if exact:
        offsets=[offset]
    else:
        first=int(np.searchsorted(recording.times[:recording.n],recording.meta['start']+offset))
        offsets=(recording.times[first:recording.n:300]-recording.meta['start']).tolist()
    for value in offsets:
        if value+10 > offset+request['duration_seconds']+1e-6:break
        if cancelled():raise Cancelled()
        check=inspect_window(recording,key,float(value),require_calibration=False)
        if check['status']!='ready':last_reason=' '.join(check['reasons']);continue
        if check['offset_seconds']+10 > offset+request['duration_seconds']+1e-6:
            last_reason='Nao ha 10 s completos dentro da janela escolhida apos a lacuna.';continue
        count=1 if key=='ecgfounder_1l' else 2
        error=technical_quality(recording.raw[check['first_sample']:check['last_sample'],:count])
        if error:last_reason=error;continue
        return check,None
    return None,last_reason


def _legacy_analysis(recording,emit=lambda item:None,cancelled=lambda:False,infer=worker_scores, *, technical_mode=False, offset=0., duration=None):
    request=scope(recording,offset,duration)
    source_key=analysis_key(recording) if recording is not None else None
    result=dict(status='running',mode='technical' if technical_mode else 'normal',evidence=evidence_state(recording),
        source_key=source_key,scope=request,operational_profile=profile_info(recording),
        clinical_validation=False,measurements=measure_recording(recording,offset,duration),scenarios=[],unavailable=[],
        interpretation='Scores de pesquisa, nao probabilidades ou diagnosticos. Pressupostos operacionais separados de evidencia validada.')
    emit(dict(kind='measurements',value=result['measurements']))
    try:
        for key,spec in catalog()['models'].items():
            if cancelled():raise Cancelled()
            signs_for_normal=normal_signs(recording,key) if recording is not None else None
            if not technical_mode and recording is not None and signs_for_normal is None:
                missing=[v for v in model_channels(key) if result['evidence']['decoder'][v] is None]
                item=dict(model=key,reason='Referencia do decoder ausente: '+', '.join(missing)+'. Selecione o perfil de pesquisa estimada para usar pressupostos operacionais.')
                result['unavailable'].append(item);emit(dict(kind='unavailable',value=item));continue
            check,reason=first_window(recording,key,cancelled,offset=offset,duration=duration,
                                     exact=request['duration_seconds'] <= 10+1e-6)
            if check is None:
                item=dict(model=key,reason=reason);result['unavailable'].append(item);emit(dict(kind='unavailable',value=item));continue
            signs=[signs_for_normal]
            if technical_mode:
                signs=[(1,),(-1,)] if key=='ecgfounder_1l' else [(1,1),(1,-1),(-1,1),(-1,-1)]
            for sign in signs:
                if cancelled():raise Cancelled()
                name='I'+('+' if sign[0]>0 else '-')
                if len(sign)==2:name+=' II'+('+' if sign[1]>0 else '-')
                if not technical_mode:name='Sinal preservado' if empirical(recording) else 'Entrada sintetica' if recording.meta.get('synthetic') else 'Convencao referenciada'
                item=dict(model=key,name=spec['name'],leads=spec['leads'],hypothesis=name,
                    offset_seconds=check['offset_seconds'],duration_seconds=10,first_sample=check['first_sample'],last_sample_exclusive=check['last_sample'],
                    mode=result['mode'],raw_multipliers=sign,evidence=result['evidence'],operational_profile=result['operational_profile'],source_key=source_key,
                    status='synthetic' if recording.meta.get('synthetic') else 'unvalidated_experiment',scores=[])
                emit(dict(kind='progress',value=spec['name']))
                values=model_values(recording,key,check['first_sample'],check['last_sample'],signs=sign if technical_mode else None)
                try:
                    cached=None
                    if infer is worker_scores and not technical_mode:
                        for previous in getattr(recording,'_analysis_cache',{}).values():
                            if previous.get('source_key')!=source_key:continue
                            cached=next((v for v in previous.get('scenarios',[]) if v['model']==key and v['offset_seconds']==item['offset_seconds'] and v.get('scores')),None)
                            if cached:break
                    response=cached if cached is not None else infer(key,values,cancelled)
                    item.update(scores=response['scores'],checkpoint_sha256=response['checkpoint_sha256'],
                        preprocessing=response['preprocessing'],runtime=response['runtime'],elapsed_seconds=response.get('elapsed_seconds'),cached=cached is not None)
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    item.update(status='unavailable',reason=str(exc))
                result['scenarios'].append(item);emit(dict(kind='scenario',value=item))
        result['status']='completed'
    except Cancelled:result['status']='cancelled'
    return result


def analysis_key(recording,technical_mode=False, *, offset=0.,duration=None):
    """Signal, contact, evidence, active processing, trained heads and requested scope."""
    import hashlib
    from .global_median import VERSION
    metadata=dict(meta=recording.meta,profile=profile_info(recording),scope=scope(recording,offset,duration),
                  mode=technical_mode,catalog=catalog(),version=f'{__version__}-{VERSION}',
                  review_as_di=recording.review_as_di)
    digest=hashlib.sha256(json.dumps(metadata,sort_keys=True).encode())
    for values in (recording.raw,recording.times,recording.quality,recording.lead_modes):
        digest.update(values[:recording.n].tobytes())
    # The effective filtered stream is included even if an external caller altered it.
    if empirical(recording):digest.update(recording.filtered[:recording.n].tobytes())
    return digest.hexdigest()


def cache_analysis(recording,result):
    if recording is None or result.get('status')!='completed' or result.get('mode')!='normal':return False
    if result.get('source_key')!=analysis_key(recording):return False
    request=result['scope'];key=analysis_key(recording,offset=request['offset_seconds'],duration=request['duration_seconds'])
    cache=getattr(recording,'_analysis_cache',{});cache[key]=result
    while len(cache)>8:del cache[next(iter(cache))]
    recording._analysis_cache=cache;recording._automatic_analysis=result;recording._automatic_analysis_key=key
    return True


def cached_analysis(recording,offset=0.,duration=None):
    key=analysis_key(recording,offset=offset,duration=duration)
    if getattr(recording,'_automatic_analysis_key',None)==key:
        result=getattr(recording,'_automatic_analysis',None)
        if result and result.get('mode')=='normal' and result.get('status')=='completed':return result
    return getattr(recording,'_analysis_cache',{}).get(key)


def automatic_analysis(recording,emit=lambda item:None,cancelled=lambda:False,infer=worker_scores, *, technical_mode=False,offset=0.,duration=None,qt_infer=None,include_models=False):
    if technical_mode:
        return _legacy_analysis(recording,emit,cancelled,infer,technical_mode=True,offset=offset,duration=duration)
    from .review_analysis import analyze_review
    return analyze_review(recording,emit,cancelled,infer,qt_infer,offset,duration,include_models)
