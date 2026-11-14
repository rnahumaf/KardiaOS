"""Research measurements per independent limb lead; explicit availability per result."""
from collections import Counter
import numpy as np
from scipy.signal import welch
from .orientation import evidence_state
from .processing import empirical,profile_info,scope
from .delineation import FS,PIPELINE,METHOD_VERSION,delineate,aggregate

NAMES={'heart_rate':('FC por RR mediano','bpm'),'p_duration':('Duração P','ms'),
       'qrs_duration':('Duração QRS','ms'),'qt':('QT','ms'),'qtc_f':('QTc Fridericia','ms')}
METHOD='Limites por batimento; derivadas gaussianas e proeminência; mediana em uma derivação'
REASONS={'short_window':'Janela de onda insuficiente.', 'low_contrast':'Onda ausente ou sem contraste suficiente.',
         'boundary_at_edge':'Limite não separado da borda ou da onda adjacente.',
         'biphasic_or_adjacent':'Onda bifásica ou sobreposta; limites ambíguos.',
         'unclosed_wave':'Retorno da onda não delimitado.', 'threshold_unstable':'Limites sensíveis ao limiar de delineação.',
         'duration_limit':'Fora dos limites técnicos de duração.', 'anchor_outside':'QRS candidato fora dos limites detectados.'}

def descriptions(result):
    """Descriptions of measured criteria, never a disease/rhythm diagnosis."""
    lead='D'+result['lead'];q=result['metrics']['qrs_duration'];value=q['value']
    if value is None:
        width=dict(id='qrs_width',status='unavailable',text=f'QRS em {lead}: duração indisponível.',reason=q['reason'])
    else:
        lower,upper=q.get('iqr_ms',[value,value]);margin=2*1000/FS
        if abs(value-120)<=margin or lower<=120<=upper:
            text=f'QRS em {lead} próximo de 120 ms; critério indeterminado.'
        elif value>120:
            text=f'QRS em {lead} ≥120 ms; duração aumentada pelo limiar adulto.'
        else:text=f'QRS em {lead} <120 ms; medida restrita à derivação.'
        width=dict(id='qrs_width',status='descriptive',text=text,
                   criterion='Referência adulta de 120 ms; não é medida global de 12 derivações nem confirmação de bloqueio.')
    return [width,
        dict(id='bundle_branch',status='unavailable',text='Bloqueio de ramo específico: indisponível.',
             reason='Requer critérios morfológicos e derivações precordiais V1/V2/V5/V6, ausentes. QRS largo isolado não os substitui.'),
        dict(id='st',status='unavailable',text='Interpretação de ST: indisponível.',
             reason='Amplitude/orientação e resposta do aparelho não validadas; o filtro visual causal altera ST. Não há inferência de infarto.'),
        dict(id='qtc_classification',status='unavailable',text='Classificação de QTc: indisponível.',
             reason='QTcF é uma estimativa por derivação; idade, sexo, contexto e QT global não estabelecidos.')]

def empty(reason,lead='I'):
    result=dict(status='unavailable',lead=lead,method=METHOD,method_version=METHOD_VERSION,
        pipeline=dict(PIPELINE),timebase='300 Hz nominais; resolução amostral 3,33 ms; relógio físico não validado',
        calibration='Tempos invariantes a ganho positivo e inversão global; não validam mV nem convenção do decoder.',
        metrics={k:dict(name=n,unit=u,value=None,status='unavailable',reason=reason) for k,(n,u) in NAMES.items()},
        notes=['Medições experimentais por derivação, não globais de 12 derivações.',
               'QTcF = QT(ms)/RR(s)^(1/3). Limites e fórmula não constituem diagnóstico.'],
        fiducials=[],detected_peaks=[])
    result['descriptions']=descriptions(result)
    return result


def technical_quality(raw):
    """Gross artifact screen, not a clinical quality score or rhythm classifier."""
    x = np.asarray(raw, dtype=float)
    if x.ndim == 1: x = x[:, None]
    if not np.isfinite(x).all() or len(x) < 600: return 'Sinal ausente, curto ou não finito.'
    if np.any(np.std(x, axis=0) < 3): return 'Sinal constante ou variação digital insuficiente.'
    if np.any(np.abs(x) >= 32760): return 'Saturação digital no trecho.'
    f, power = welch(x, fs=FS, nperseg=min(900, len(x)), axis=0, detrend='linear')
    useful = power[(f >= 5) & (f <= 40)].sum(axis=0)
    high = power[f >= 45].sum(axis=0)
    if np.any(high / np.maximum(useful, 1e-20) > .5): return 'Energia de alta frequência excessiva; ruído/artefato.'
    return None


def stable_segment(recording, seconds=30, offset=0., duration=None, lead="I"):
    r = recording
    if r is None or not r.n or r.meta.get('start') is None: return None, 'Sem captura estabilizada.'
    if r.meta.get('sample_rate') != FS: return None, 'Frequência diferente de 300 Hz; base temporal incompatível.'
    t = r.times[:r.n]
    if not np.isfinite(t).all() or np.any(np.diff(t) <= 0): return None, 'Base temporal inválida.'
    request=scope(r,offset,duration)
    begin=float(r.meta['start'])+request['offset_seconds']
    start = int(np.searchsorted(t, begin))
    end = int(np.searchsorted(t, begin+request['duration_seconds']-1e-7, side='right'))
    channel = 0 if lead == 'I' else 1
    mode = 1 if lead == 'I' else 6
    good = r.quality[:r.n] & (r.lead_modes[:r.n] >= mode) & ((r.raw[:r.n, channel] & 3) == 0)
    good[:start] = False; good[end:] = False
    breaks = np.flatnonzero(~np.isclose(np.diff(t), 1 / FS, rtol=0, atol=1e-6)) + 1
    cuts = sorted(set([0, r.n, *breaks.tolist(), *(np.flatnonzero(np.diff(good.astype(int)))+1).tolist()]))
    segments = [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a and good[a] and good[a:b].all()]
    if not segments: return None, f'Sem trecho contínuo com contato aceito em D{lead}.'
    a, b = max(segments, key=lambda ab: (ab[1] - ab[0], -ab[0]))
    if b - a < 10 * FS: return None, 'São necessários pelo menos 10 s contínuos com contato aceito.'
    return (a, min(b, a + seconds * FS)), None



def _measure_lead(recording,offset=0.,duration=None,lead='I'):
    if lead not in ('I','II'):raise ValueError('Medições disponíveis apenas nos canais I e II, sem síntese de precordiais.')
    result=empty('Limites de onda ainda não determinados.',lead)
    result['operational_profile']=profile_info(recording)
    segment,error=stable_segment(recording,offset=offset,duration=duration,lead=lead)
    def fail(reason):
        for m in result['metrics'].values():m.update(value=None,status='unavailable',reason=reason)
        result['descriptions']=descriptions(result)
        return result
    if error:return fail(error)
    a,b=segment;channel=0 if lead=='I' else 1
    result.update(first_sample=a,last_sample_exclusive=b,offset_seconds=float(recording.times[a]-recording.meta['start']),
        duration_seconds=(b-a)/FS,synthetic=bool(recording.meta.get('synthetic')),
        amplitude_verified=False if empirical(recording) else evidence_state(recording)['amplitude'][lead])
    raw=recording.raw[a:b,channel].astype(float)
    error=technical_quality(raw)
    if error:return fail(error)
    calculated=delineate(raw);values=aggregate(calculated)
    result['detected_peaks']=[int(a+p) for p in calculated['peaks']]
    result['fiducials']=[{k:(int(a+v) if k!='reason' else dict(v)) for k,v in beat.items()} for beat in calculated['beats']]
    result['candidate_beats']=len(calculated['beats'])
    if not values:return fail('QRS candidatos instáveis ou sem repetibilidade/contraste suficiente para medir.')
    beats=calculated['beats'];rr=np.asarray(calculated['rr'])
    result.update(status='experimental',beats=len(beats),rr_variability=float(np.std(rr)/np.mean(rr)))
    for key,val in values.items():
        result['metrics'][key].update(value=round(float(val),1),status='experimental',reason='')
    result['metrics']['heart_rate'].update(rr_median_seconds=float(np.median(rr)),beats=len(beats),method='60 / mediana dos RR aceitos')
    for key,on,off,wave in [('qrs_duration','qon','qoff','qrs'),('p_duration','pon','poff','p'),('qt','qon','toff','t')]:
        durations=[(v[off]-v[on])/FS*1000 for v in beats if on in v and off in v]
        metric=result['metrics'][key];metric.update(accepted_beats=len(durations),candidate_beats=len(beats),lead=lead)
        if durations:metric['iqr_ms']=[float(v) for v in np.percentile(durations,[25,75])]
        if key not in values:
            problems=Counter(v['reason'].get(wave,'') for v in beats if v['reason'].get(wave))
            why=REASONS.get(problems.most_common(1)[0][0],'Limites insuficientes.') if problems else 'Duração ou posição da onda variável entre batimentos.'
            metric['reason']=f'{len(durations)}/{len(beats)} batimentos delimitados. '+why
            metric['rejected_reasons']=dict(problems)
    qt=result['metrics']['qt'];qrs=result['metrics']['qrs_duration'];qtc=result['metrics']['qtc_f']
    if qt['value'] is None:qtc['reason']='QT indisponível: '+qt['reason']
    elif qrs['value'] is None:qtc['reason']='QRS sem duração confiável; QTc não aplicado.'
    elif result['rr_variability']>.10 or not .6<=np.median(rr)<=1.5 or qrs['value']>=120:
        qtc['reason']='QTc não aplicado: RR variável, RR fora de 0,6–1,5 s ou QRS ≥120 ms.'
    else:qtc.update(value=round(values['qt']/np.cbrt(np.median(rr)),1),status='experimental',reason='',
                    formula='QTcF = QT(ms) / RR(s)^(1/3)',lead=lead,accepted_beats=qt['accepted_beats'])
    result['descriptions']=descriptions(result)
    return result

def measure_recording(recording,offset=0.,duration=None,*,lead='I',include_other=True):
    """Independent I/II results. Additional leads are never merged into a global QT/QRS."""
    result=_measure_lead(recording,offset,duration,lead)
    result['additional_leads']=[]
    if include_other and lead=='I' and recording is not None and recording.n and np.any(recording.lead_modes[:recording.n]==6):
        result['additional_leads'].append(_measure_lead(recording,offset,duration,'II'))
    return result
