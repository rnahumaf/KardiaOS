"""Technical sensitivity of median landmarks; not a probability of correctness.

Four deterministic, correlated subset medians retain the common beat alignment.
Observed ranges are sensitivity envelopes, never clinical confidence intervals.
"""
import numpy as np
from .median_landmarks import smooth_median, delineate_medians

VERSION = 'median-stability-1'
MIN_BEATS = 10
LIMIT_SAMPLES = dict(pon=6, poff=6, qon=3, qoff=3, ton=9, toff=9)
LABELS = dict(pon='Início de P', poff='Fim de P', qon='Início do QRS',
              qoff='Fim do QRS', ton='Início de T', toff='Fim de T')
INTERVALS = dict(p_duration=('pon','poff'), qrs_duration=('qon','qoff'),
                 pr=('pon','qon'), qt=('qon','toff'), qtc_f=('qon','toff'))


def assess(stacks, names, anchor, rr, points, sources, factor, cancelled=lambda:False):
    from .automatic_analysis import Cancelled
    from .rule_analysis import features
    n=len(stacks.get('qrs',[]))
    result=dict(version=VERSION,accepted_beats=n,minimum_beats=MIN_BEATS,
                subsets=[],boundaries={},replicates=[],clinical_validation=False)
    groups=[] if n<MIN_BEATS else [('primeira metade',np.arange(n//2)),
        ('segunda metade',np.arange(n//2,n)),('alternados pares',np.arange(0,n,2)),
        ('alternados ímpares',np.arange(1,n,2))]
    for name,indices in groups:
        if cancelled():raise Cancelled()
        medians={lead:{kind:smooth_median(np.median(stacks[kind][indices,:,ch],axis=0))[0]
                      for kind in ('qrs','pt')} for ch,lead in enumerate(names)}
        p,_,_=delineate_medians(medians,anchor,rr)
        values={key:round((p[off]-p[on])/.3,1) if on in p and off in p else None
                for key,(on,off) in INTERVALS.items()}
        values['qtc_f']=round(values['qt']/np.cbrt(rr),1) if values['qt'] is not None and values['qrs_duration'] is not None and values['qrs_duration']<120 else None
        reps={lead:dict(values_mv=m['qrs']*factor,pt_values_mv=m['pt']*factor,
                       aligned_beats_mv=stacks['qrs'][indices,:,ch]*factor)
              for ch,(lead,m) in enumerate(medians.items())}
        result['subsets'].append(dict(name=name,beat_count=len(indices)))
        result['replicates'].append(dict(points=p,values=values,
            features=features(dict(global_fiducials=p),reps)))
    for key,label in LABELS.items():
        if key not in points:
            result['boundaries'][key]=dict(status='unavailable',reason=label+' indisponível.');continue
        source=sources.get(key,{})
        contrast=min((source.get('quality',{}).get(l,0) for l in source.get('supporting_leads',[])),default=0)
        detected=[v['points'][key] for v in result['replicates'] if key in v['points']]
        positions=[points[key],*detected];span=max(positions)-min(positions)
        reasons=[]
        if not groups:reasons.append('Estabilidade não verificada: poucos batimentos')
        else:
            if len(detected)!=len(groups):reasons.append(f'{label} não reproduzido em {len(groups)-len(detected)}/{len(groups)} subconjuntos')
            if span>LIMIT_SAMPLES[key]:reasons.append(f'{label} instável: variação de {span/.3:.1f} ms')
            if contrast<12:reasons.append(f'{label} com baixo contraste')
        result['boundaries'][key]=dict(status='unverified' if not groups else 'review' if reasons else 'stable',
            reason='; '.join(reasons),contrast=round(contrast,2),detected_subsets=len(detected),
            total_subsets=len(groups),range_ms=[round((v-anchor)/.3,1) for v in (min(positions),max(positions))],
            spread_ms=round(span/.3,1),limit_ms=round(LIMIT_SAMPLES[key]/.3,1),
            range_samples=[min(positions),max(positions)])
    return result


def attach_metrics(measurement, quality):
    measurement['technical_quality']=quality
    for key,deps in INTERVALS.items():
        metric=measurement['metrics'][key]
        if metric['value'] is None:continue
        boundaries=[quality['boundaries'][v] for v in deps]
        reasons=list(dict.fromkeys(v['reason'] for v in boundaries if v['reason']))
        if quality['replicates'] and key=='qtc_f' and any(v['values'][key] is None for v in quality['replicates']):
            reasons.append('Correção QTc indisponível em um ou mais subconjuntos')
        values=[metric['value']]+[v['values'][key] for v in quality['replicates'] if v['values'][key] is not None]
        state='unverified' if any(v['status']=='unverified' for v in boundaries) else 'review' if reasons else 'stable'
        metric.update(status='estimated',quality=dict(status=state,reason='; '.join(reasons),
            range_ms=[min(values),max(values)],spread_ms=round(max(values)-min(values),1),
            verified_subsets=sum(v['values'][key] is not None for v in quality['replicates'])))


def warning(metric):
    return metric.get('quality',{}).get('reason','')


def alerts(measurement):
    return list(dict.fromkeys(v['reason'] for v in measurement.get('technical_quality',{}).get('boundaries',{}).values()
                             if v['status'] in ('review','unverified') and v.get('reason')))


def detail(metric):
    quality=metric.get('quality')
    if not quality:return ''
    text=quality['reason']
    if quality['status']!='unverified':
        lo,hi=quality['range_ms']
        text+=(('. ' if text else '')+f'Faixa observada entre medianas: {lo:g}–{hi:g} ms; {quality["verified_subsets"]}/4 subconjuntos. Não é intervalo de confiança clínica.')
    return text


RULE_BOUNDARIES = {
    'pr_short':('pon','qon'), 'pr_long':('pon','qon'), 'qrs_wide':('qon','qoff'),
    'p_wide':('pon','poff'), 'qt_long':('qon','qoff','toff'),
    'p_tall':('pon','poff','qon'), 'p_biphasic':('pon','poff','qon'),
    'q_prominent':('poff','qon','qoff'), 'j_elevation':('poff','qon','qoff'),
    'st_depression':('poff','qon','qoff','ton'),
    't_inversion':('poff','qon','ton','toff'), 't_tall':('poff','qon','ton','toff'),
    't_biphasic':('poff','qon','ton','toff'), 't_notched':('poff','qon','ton','toff')}


def guard_rules(recording, measurement, rows):
    from .rule_analysis import classify
    quality=measurement.get('technical_quality')
    if not quality:return
    variants=[]
    for replica in quality['replicates']:
        m=dict(measurement,metrics={k:dict(v,value=replica['values'].get(k,v['value'])) for k,v in measurement['metrics'].items()})
        variants.append({v['id']:v for v in classify(recording,m,{},feature_data=replica['features'],check_stability=False)['rules']})
    for row in rows:
        deps=RULE_BOUNDARIES.get(row['id'])
        if not deps or row['status']=='unavailable':continue
        boundaries=[quality['boundaries'][k] for k in deps]
        reason=''
        if any(v['status']=='unverified' for v in boundaries):reason='Estabilidade não verificada: poucos batimentos.'
        elif any(v['status']=='unavailable' or v.get('detected_subsets',0)<4 for v in boundaries):reason='Marcos necessários não reproduzidos em todos os subconjuntos.'
        elif any(v.get('contrast',0)<12 for v in boundaries):reason='Marcos necessários com baixo contraste.'
        elif any(v[row['id']]['status']!=row['status'] for v in variants):reason='A variação entre medianas atravessa o limiar ou muda a avaliação deste critério.'
        if reason:row.update(status='unavailable',reason=reason,technical_status='indeterminate',central_status=row['status'])
