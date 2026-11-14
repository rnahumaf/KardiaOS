"""Automatic synchronized10s selection, blind to model scores and QT values."""
import numpy as np
from .qt_templates import build,quality
from .measurements import technical_quality
from .signal import FS

T_FLAGS={'T_contrast_absent_or_low','T_dispersion_blurring','possible_T_alternation','T_polarity_disagreement'}

def signal_features(entries):
    result={}
    for lead,entry in entries.items():
        q=entry['quality'];template=entry['template'];groups=template['groups'];g=groups[0] if groups else None
        enough=bool(g and g['n_beats']>=5 and g['n_beats']>=.5*template.get('eligible_beats',0))
        flags=sorted(T_FLAGS.intersection(g['reasons'])) if g else ['no_group']
        result[lead]=dict(signal_eligible=q['eligible'],repolarization_stable=enough and not flags,
            signal_quality_score=q['score'],waveform_flags=flags)
    return result

def select_lead(entries):
    features=signal_features(entries);valid=[l for l,v in features.items() if v['signal_eligible']]
    lead=max(valid,key=lambda l:(features[l]['repolarization_stable'],features[l]['signal_quality_score'],l=='I')) if valid else None
    return lead,features

def rank(entries):
    features=signal_features(entries)
    if not features or not all(v['signal_eligible'] for v in features.values()):return None
    values=[v['signal_quality_score'] for v in features.values()]
    return sum(v['repolarization_stable'] for v in features.values()),min(values),float(np.mean(values))

def recording_scope(r):
    if r is None or not r.n or r.meta.get('start') is None:raise ValueError('Sem gravação para laudo.')
    if r.meta.get('sample_rate')!=300:raise ValueError('Frequência incompatível.')
    times=r.times[:r.n]
    if not np.isfinite(times).all() or np.any(np.diff(times)<=0):raise ValueError('Base temporal inválida.')
    begin=float(r.meta['start']);end=min(float(r.meta.get('end') or r.last_time),r.last_time)+1/300
    if end-begin<10-1e-6:raise ValueError('São necessários pelo menos 10 s de gravação para gerar um laudo.')
    return begin,end

def trace_window(r,offset=0.,duration=None):
    begin,end=recording_scope(r);start=begin+offset;stop=min(end,start+(duration if duration is not None else end-start))
    if stop-start<10-1e-6:raise ValueError('São necessários pelo menos 10 s de gravação para gerar um laudo.')
    times=r.times[:r.n];a=int(np.searchsorted(times,start-1e-7));b=int(np.searchsorted(times,start+10-1e-7))
    mode='six' if a<b and (r.lead_modes[a:b]==6).all() else 'di'
    return dict(first_sample=a,last_sample_exclusive=b,offset_seconds=float(offset),duration_seconds=10.,
        layout=mode,analysis_eligible=False,reason='Sem janela comum de qualidade suficiente; somente traçado.')

def select_window(r,cancelled=lambda:False,emit=lambda text:None,offset=0.,duration=None):
    from .automatic_analysis import Cancelled
    fallback=trace_window(r,offset,duration);begin,end=recording_scope(r);t=r.times[:r.n]
    start=begin+offset;stop=min(end,start+(duration if duration is not None else end-start))
    first=int(np.searchsorted(t,start-1e-7));last=int(np.searchsorted(t,stop-1e-7))
    two=bool((r.lead_modes[first:last]==6).any());leads=['I','II'] if two else ['I'];count=len(leads)
    if last-first<3000:return fallback,None,[]
    starts=sorted(set(range(first,last-3000+1,300))|{last-3000})
    candidates=[];best=None;best_rank=None;entries_best=None
    for number,a in enumerate(starts):
        if cancelled():raise Cancelled()
        if number%20==0:emit('Selecionando janela comum de 10 s')
        b=a+3000;raw=r.raw[a:b,:count].astype(float)
        if not r.quality[a:b].all() or not np.all(r.lead_modes[a:b]>=(6 if two else 1)) or np.any((r.raw[a:b,:count]&3)!=0):continue
        if not np.allclose(np.diff(t[a:b]),1/300,atol=1e-6,rtol=0) or technical_quality(raw):continue
        entries={lead:dict(quality=quality(raw[:,ch]),template=build(raw[:,ch])) for ch,lead in enumerate(leads)}
        score=rank(entries);candidates.append(dict(first_sample=a,offset_seconds=float(t[a]-begin),quality_rank=score))
        if score is not None and (best_rank is None or score>best_rank):
            best=dict(first_sample=a,last_sample_exclusive=b,offset_seconds=float(t[a]-begin),duration_seconds=10.,
                layout='six' if two else 'di',analysis_eligible=True,native_leads=leads,reason='')
            best_rank=score;entries_best=entries
    return best or fallback,entries_best,candidates

def template_supported(entry):
    groups=entry['template']['groups']
    return bool(entry['quality']['eligible'] and groups and groups[0].get('visual_eligible',groups[0]['technical_eligible']))
