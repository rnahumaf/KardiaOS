"""Exploratory review, exact common window, independent result availability."""
import json,uuid
import numpy as np
from .research import catalog,inspect_window
from .processing import profile_info,model_values,scope,empirical,scale_and_signs
from .orientation import evidence_state,normal_signs
from .measurements import measure_recording,empty
from .review_window import select_window,select_lead,template_supported
from .qt_templates import build,quality,combine,label
from .review_signal import waveform_values,PIPELINE_VERSION
from .signal import six_leads
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
    from .qt_client import infer_qt,WEIGHT_SHA256
    r=recording;key=analysis_key(r) if r is not None else None
    request=scope(r,offset,duration)
    result=dict(status='running',mode='normal',version='0.8.1',run_id=uuid.uuid4().hex,source_key=key,scope=request,
        evidence=evidence_state(r),operational_profile=profile_info(r),clinical_validation=False,
        measurements=empty('Análise em preparação.'),scenarios=[],unavailable=[],representative={},hypotheses=[],
        qtc_label='QTc: erro na estimativa',selected_lead=None,report_window=None,
        exploratory_policy=dict(id='template083-own082',confidence_calibrated=False,clinical_qualification=False),
        review_pipeline=dict(id=PIPELINE_VERSION,phase='zero phase on completed native-time segments',filters=r.config.to_dict() if r else {}))
    def progress(text):emit(dict(kind='progress',value=text))
    try:
        if cancelled():raise Cancelled()
        try:window,entries,candidates=select_window(r,cancelled,progress,offset,duration)
        except ValueError as exc:
            result.update(status='completed',reason=str(exc),reportable=False)
            result['measurements']=empty(str(exc));entries=None;window=None;candidates=[]
        result['report_window']=window;result['window_selection']=dict(candidates=candidates,criterion='observed T stability, worst native-lead quality, mean, earliest tie; no QT or model scores')
        if window is None or not window['analysis_eligible']:
            reason=result.get('reason') or window['reason'];result['measurements']=empty(reason)
            result.update(status='completed',reportable=window is not None,trace_only=window is not None)
            result['unavailable']=[dict(model=k,reason=reason) for k in catalog()['models']]
            emit(dict(kind='measurements',value=result['measurements']));return json_value(result)
        result.update(reportable=True,trace_only=False)
        a,b=window['first_sample'],window['last_sample_exclusive'];selected,features=select_lead(entries)
        result.update(selected_lead=selected,lead_selection=features)
        m=measure_recording(r,window['offset_seconds'],10)
        measured={v['lead']:v for v in [m]+m.get('additional_leads',[])}
        progress('Estimando QT com modelo local e template')
        count=len(window['native_leads']);_,signs=scale_and_signs(r)
        oriented=r.raw[a:b,:count].astype(float)*np.asarray(signs[:count])
        neural=None;qt_error=''
        try:
            if not empirical(r) and not r.meta.get('synthetic') and normal_signs(r,'ecgfounder_1l' if count==1 else 'deeppsp_2l') is None:
                raise ValueError('Convenção do decoder não referenciada neste perfil.')
            neural=(qt_infer or infer_qt)(oriented,cancelled)
            if neural.get('checkpoint_sha256')!=WEIGHT_SHA256 or len(neural.get('leads',[]))!=count:raise ValueError('Checkpoint QT incompatível.')
        except (ValueError,OSError,KeyError,TypeError) as exc:qt_error=str(exc)
        if cancelled():raise Cancelled()
        qt_results={}
        for ch,lead in enumerate(window['native_leads']):
            entry=entries[lead];groups=entry['template']['groups']
            model=neural['leads'][ch] if neural else dict(metrics={},beats=[])
            value=combine(groups[0],model) if groups else dict(qtc_f=None,technical_estimate=False,reasons=['no_supported_group'])
            if qt_error:value['reasons'].append(qt_error)
            value.update(confidence_calibrated=False,mode='exploratory',source_first_sample=a,source_last_sample_exclusive=b)
            entry.update(result=value,model_fiducials=model['beats'],label=label(lead,value));qt_results[lead]=entry
            if lead in measured:
                item=measured[lead]
                for name,number in [('qt',value.get('qt_template') if value.get('technical_estimate') else None),('qtc_f',value.get('qtc_f'))]:
                    item['metrics'][name].update(value=round(number,1) if number is not None else None,
                        status='exploratory_low_confidence' if number is not None else 'unavailable',
                        reason='' if number is not None else '; '.join(value.get('reasons',[])),
                        method='Template predominante + CompactSegmenter082',confidence_calibrated=False,
                        unavailable_scope='technical_quality' if number is None else None)
                item['exploratory_qt']=dict(value,checkpoint_sha256=WEIGHT_SHA256)
                item['qtc_label']=entry['label']
        if selected:result['qtc_label']=qt_results[selected]['label']
        result.update(measurements=m,qt=dict(checkpoint_sha256=WEIGHT_SHA256,leads=qt_results,worker_error=qt_error))
        emit(dict(kind='measurements',value=m))
        # Source samples and review filters are identical to the screen/report.
        display=waveform_values(r,a,b,raw=False);raw_display=waveform_values(r,a,b,raw=True)
        native_six=six_leads(r.raw[a:b].astype(float)*np.asarray(signs))
        names=['I','II','III','aVR','aVL','aVF'] if count==2 else ['I']
        for ch,lead in enumerate(names):
            if cancelled():raise Cancelled()
            entry=entries.get(lead)
            if entry is None:entry=dict(quality=quality(native_six[:,ch]),template=build(native_six[:,ch]))
            if not template_supported(entry):continue
            group=entry['template']['groups'][0];pre=group['r_index'];width=len(group['raw_median'])
            intervals=[(int(p-pre),int(p-pre+width)) for p in group['centers']]
            filtered=np.median(np.stack([display[x:y,ch] for x,y in intervals]),axis=0)
            native=np.median(np.stack([raw_display[x:y,ch] for x,y in intervals]),axis=0)
            if not np.isfinite(filtered).all() or not np.isfinite(native).all():continue
            markers=[]
            if lead==selected and qt_results[lead]['result'].get('technical_estimate'):
                for kind in ('qon','toff'):
                    p=group['candidate'][kind];markers.append(dict(kind=kind,index=p,time_seconds=(p-pre)/300))
            result['representative'][lead]=dict(values_mv=filtered,raw_values_mv=native,time_seconds=group['time_seconds'],markers=markers,
                group_size=group['n_beats'],discarded_beats=entry['template']['discarded_from_dominant'],
                source_first_sample=a,source_last_sample_exclusive=b,source_beat_indices=group['beat_indices'],
                source_centers=group['centers'],translation_samples=group['shift_samples'],
                median_operation='pointwise; no amplitude normalization or temporal warp',clinical_confidence=False,
                visual_eligible=group['visual_eligible'],measurement_eligible=group['technical_eligible'],measurement_reasons=group['reasons'],
                template_measurement_pipeline='QRS0.5–80Hz; T0.5–30Hz; zero phase',display_pipeline=result['review_pipeline'])
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
