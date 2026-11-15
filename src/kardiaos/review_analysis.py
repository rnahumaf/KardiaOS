"""Exploratory review, exact common window, independent result availability."""
import json,uuid
import numpy as np
from .research import catalog,inspect_window
from .processing import profile_info,model_values,scope,empirical
from .orientation import evidence_state,normal_signs
from .measurements import empty
from .global_median import analyze as analyze_medians, VERSION
from .review_window import select_window
from .review_signal import PIPELINE_VERSION
from .hypotheses import merge_hypotheses,visible_hypotheses

def json_value(value):
    if isinstance(value,np.ndarray):return json_value(value.tolist())
    if isinstance(value,np.generic):return json_value(value.item())
    if isinstance(value,dict):return {str(k):json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_value(v) for v in value]
    if isinstance(value,float) and not np.isfinite(value):raise ValueError('Nonfinite analysis result')
    return value

def analyze_review(recording,emit,cancelled,infer,qt_infer=None,offset=0.,duration=None):
    from .automatic_analysis import analysis_key,Cancelled
    r=recording;key=analysis_key(r) if r is not None else None
    request=scope(r,offset,duration)
    result=dict(status='running',mode='normal',version='0.9.0',run_id=uuid.uuid4().hex,source_key=key,scope=request,
        evidence=evidence_state(r),operational_profile=profile_info(r),clinical_validation=False,
        measurements=empty('Análise em preparação.'),scenarios=[],unavailable=[],representative={},hypotheses=[],
        qtc_label='QTc: erro na estimativa',selected_lead=None,report_window=None,
        exploratory_policy=dict(id=VERSION,confidence_calibrated=False,clinical_qualification=False),
        review_pipeline=dict(id=PIPELINE_VERSION,phase='zero phase on completed native-time segments',filters=r.config.to_dict() if r else {}))
    def progress(text):emit(dict(kind='progress',value=text))
    try:
        if cancelled():raise Cancelled()
        try:window,entries,candidates=select_window(r,cancelled,progress,offset,duration)
        except ValueError as exc:
            result.update(status='completed',reason=str(exc),reportable=False)
            result['measurements']=empty(str(exc));entries=None;window=None;candidates=[]
        result['report_window']=window;result['window_selection']=dict(candidates=candidates,criterion='joint QRS repeatability and contrast; display/models only; no individual endpoints or model scores')
        if window is None:
            result['unavailable']=[dict(model=k,reason=result.get('reason','Sem gravação elegível.')) for k in catalog()['models']]
            emit(dict(kind='measurements',value=result['measurements']));return json_value(result)
        a,b=window['first_sample'],window['last_sample_exclusive']
        progress('Alinhando a gravação completa e estimando limites globais nas medianas')
        m,representatives,audit,qtc_label=analyze_medians(r,cancelled)
        result.update(measurements=m,representative=representatives,alignment=audit,
                      selected_lead='I',qtc_label=qtc_label,reportable=True,trace_only=not bool(representatives),
                      qt=dict(method=VERSION,source='global_medians_only',neural_segmenter_used=False))
        # A report-window quality decision cannot invalidate whole-record medians.
        window['analysis_eligible']=bool(representatives)
        emit(dict(kind='measurements',value=m))
        if not representatives:
            result.update(status='completed')
            result['unavailable']=[dict(model=k,reason='Sem conjunto de batimentos completos.') for k in catalog()['models']]
            return json_value(result)
        result['templates_complete']=True
        for model,spec in catalog()['models'].items():
            if cancelled():raise Cancelled()
            check=inspect_window(r,model,window['offset_seconds'],require_calibration=False)
            signs_normal=normal_signs(r,model)
            if check['status']!='ready' or signs_normal is None or check.get('first_sample')!=a or check.get('last_sample')!=b:
                reason='; '.join(check.get('reasons',[])) or 'Derivações/convenção indisponíveis na janela comum.'
                value=dict(model=model,reason=reason);result['unavailable'].append(value);emit(dict(kind='unavailable',value=value));continue
            item=dict(model=model,name=spec['name'],leads=spec['leads'],hypothesis='Sinal preservado' if empirical(r) else 'Convenção referenciada',
                offset_seconds=window['offset_seconds'],duration_seconds=10,first_sample=a,last_sample_exclusive=b,
                mode='normal',raw_multipliers=signs_normal,evidence=result['evidence'],operational_profile=result['operational_profile'],
                source_key=key,status='synthetic' if r.meta.get('synthetic') else 'unvalidated_experiment',scores=[])
            progress(spec['name'])
            try:
                response=infer(model,model_values(r,model,a,b),cancelled)
                item.update(scores=response['scores'],checkpoint_sha256=response['checkpoint_sha256'],preprocessing=response['preprocessing'],
                    runtime=response['runtime'],elapsed_seconds=response.get('elapsed_seconds'),cached=False)
            except (OSError,ValueError,KeyError,TypeError) as exc:item.update(status='unavailable',reason=str(exc))
            result['scenarios'].append(item);emit(dict(kind='scenario',value=item))
        merged=merge_hypotheses(result['scenarios'],a,b,catalog())
        result.update(hypotheses=visible_hypotheses(merged),hypothesis_provenance=merged,status='completed')
    except Cancelled:result.update(status='cancelled',hypotheses=[],qtc_label='QTc: erro na estimativa')
    return json_value(result)
