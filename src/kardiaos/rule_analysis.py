"""Auditable, exploratory rules on synchronized medians and original RR.

Thresholds and limitations are documented in docs/rules-0100.md. Missing data
never counts as a negative rule. No diagnosis of infarction or chamber disease.
"""
import numpy as np
from scipy.signal import find_peaks
from .median_landmarks import mad
from .orientation import normal_signs

VERSION = 'limb-rules-2'
GROUPS = [('I', 'aVL'), ('II', 'III', 'aVF')]


def context(recording):
    value = recording.meta.get('clinical_context', {}) if recording else {}
    if not isinstance(value, dict): value = {}
    age = value.get('age_years'); sex = value.get('sex')
    if isinstance(age, bool) or not isinstance(age, (int, float)) or not np.isfinite(age) or not 0 <= age <= 120: age = None
    if sex not in ('male', 'female'): sex = None
    return dict(age_years=age, sex=sex)


def contiguous(leads):
    return sorted(set().union(*(set(leads).intersection(g) for g in GROUPS if len(set(leads).intersection(g)) >= 2)))


def features(measurement, representatives):
    points = measurement.get('global_fiducials', {})
    result = {}
    for lead, rep in representatives.items():
        f = dict(lead=lead, available=False, reason='P/PR insuficientes para referência de amplitude.')
        result[lead] = f
        if not all(k in points for k in ('pon', 'poff', 'qon', 'qoff')): continue
        a, b = points['poff']+2, points['qon']-2
        if b-a < 5: continue
        q, pt = np.asarray(rep['values_mv']), np.asarray(rep['pt_values_mv'])
        qb, pb = float(np.median(q[a:b])), float(np.median(pt[a:b]))
        noise = max(mad(np.diff(pt[a:b]))/np.sqrt(2), .001)
        f.update(available=True, reason='', baseline_mv=qb, pt_baseline_mv=pb, noise_mv=noise)
        p = pt[points['pon']:points['poff']+1]-pb
        f['p_mv'] = float(p[np.argmax(abs(p))])
        f['p_biphasic'] = bool(p.max() > max(3*noise, .03) and p.min() < -max(3*noise, .03))
        # Association checks use the common P window on individual aligned curves;
        # they never delineate individual beats or alter any interval.
        beats = np.asarray(rep['aligned_beats_mv']); baseline = np.median(beats[:, a:b], axis=1)
        window = beats[:, points['pon']:points['poff']+1]-baseline[:, None]
        sign = np.sign(f['p_mv'])
        f['p_consistency'] = float(np.mean(np.max(sign*window, axis=1) > max(3*noise, .02)))
        peaks = np.argmax(sign*window, axis=1)
        f['p_peak_dispersion_ms'] = float(np.percentile(abs(peaks-np.median(peaks)),90)/.3)
        wave = q[points['qon']:points['qoff']+1]-qb
        f['qrs_mv'] = float(np.ptp(wave)); f['r_mv'] = float(max(0, wave.max()))
        threshold = max(3*noise, .01, .02*f['r_mv'])
        positive = np.flatnonzero(wave > threshold)
        first_r = int(positive[0]) if len(positive) else len(wave)
        negative = np.flatnonzero(wave[:first_r] < -threshold)
        f['q_mv'] = float(-wave[negative].min()) if len(negative) else 0.
        f['q_ms'] = float((negative[-1]-negative[0]+1)/.3) if len(negative) else 0.
        f['qs'] = bool(not len(positive) and f['q_mv'] > threshold)
        j = points['qoff']
        f['j_mv'] = float(np.mean(q[j-1:j+2])-qb)
        f['st60_mv'] = float(np.mean(q[j+17:j+20])-qb) if j+20 < points.get('ton', j) else None
        f['st_slope_mv'] = f['st60_mv']-float(np.mean(q[j+5:j+8])-qb) if f['st60_mv'] is not None else None
        if all(k in points for k in ('ton', 'toff')):
            t = pt[points['ton']:points['toff']+1]-pb
            f['t_mv'] = float(t[np.argmax(abs(t))]); f['t_duration_ms'] = (points['toff']-points['ton'])/.3
            f['t_biphasic'] = bool(t.max() > max(3*noise, .05) and t.min() < -max(3*noise, .05))
            peaks, _ = find_peaks(np.sign(f['t_mv'])*t, prominence=max(3*noise, .15*np.ptp(t)), distance=6)
            f['t_notched'] = bool(len(peaks) > 1)
        else: f['t_mv'] = None
    return result


def classify(recording, measurement, representatives):
    c = context(recording); adult = c['age_years'] is not None and c['age_years'] >= 18
    data = features(measurement, representatives); rows = []
    metrics = measurement.get('metrics', {})
    def metric(key): return metrics.get(key, {}).get('value')
    def add(key, label, detected, criterion, reason='', leads=(), amplitude=False, required=True):
        status = 'unavailable' if detected is None else 'detected' if detected else 'not_detected'
        rows.append(dict(id=key, label=label, status=status, criterion=criterion, reason=reason,
                         leads=list(leads), amplitude_estimated=amplitude, required_for_normal=required))
    adult_reason = 'Idade adulta não informada ou faixa pediátrica sem regras validadas.'
    hr, pr, qrs, pd, qtc = (metric(k) for k in ('heart_rate','pr','qrs_duration','p_duration','qtc_f'))
    rr = np.asarray(measurement.get('alignment', {}).get('rhythm', {}).get('rr_seconds', []))
    rhythm_ok = len(rr) >= 4 and np.all((rr >= .25) & (rr <= 3))
    cv = float(np.std(rr)/np.mean(rr)) if rhythm_ok else None
    regular = bool(cv <= .10 and np.max(abs(rr-np.median(rr)))/np.median(rr) <= .15) if cv is not None else None
    add('irregular', 'Ritmo irregular', None if regular is None else not regular,
        'CV dos RR >10% ou desvio máximo da mediana >15%; limiares exploratórios, sem diagnóstico de fibrilação atrial.', 'RR insuficientes.' if regular is None else '')
    for key, label, condition, criteria in [
        ('brady','Bradicardia',hr is not None and hr < 60,'FC <60 bpm em adulto.'),
        ('tachy','Taquicardia',hr is not None and hr > 100,'FC >100 bpm em adulto.'),
        ('pr_long','PR prolongado; possível atraso de condução AV',pr is not None and pr > 200,'PR global >200 ms em adulto; não determina o mecanismo.'),
        ('pr_short','PR curto',pr is not None and pr < 120,'PR global <120 ms em adulto; não diagnostica pré-excitação.'),
        ('qrs_wide','QRS alargado',qrs is not None and qrs >= 120,'QRS global ≥120 ms em adulto; sem identificação de ramo.'),
        ('p_wide','P alargada; possível atraso de condução atrial',pd is not None and pd >= 120,'P global ≥120 ms em adulto; sem diagnóstico de aumento atrial.')]:
        value = hr if key in ('brady','tachy') else pr if key.startswith('pr_') else qrs if key=='qrs_wide' else pd
        add(key,label,bool(condition) if adult and value is not None else None,criteria,
            adult_reason if not adult else 'Limites necessários indisponíveis.' if value is None else '')
    qt_limit = 450 if c['sex']=='male' else 460
    add('qt_long','QTcF prolongado',qtc >= qt_limit if adult and c['sex'] and qtc is not None else None,
        'QTcF ≥450 ms (masculino) ou ≥460 ms (feminino), adulto; condições de RR/QRS da medição mantidas.',
        adult_reason if not adult else 'Sexo de referência ou QTcF indisponível.' if not c['sex'] or qtc is None else '')
    valid = {l:f for l,f in data.items() if f['available']}
    six = all(l in valid for l in ('I','II','III','aVR','aVL','aVF'))
    orientation_ok = normal_signs(recording, 'deeppsp_2l') is not None
    for key, label, field, predicate, criterion, eligible, paired in [
        ('p_tall','P de amplitude elevada','p_mv',lambda v:v>.25,'P >0,25 mV em derivação inferior.',('II','III','aVF'),False),
        ('j_elevation','Elevação do ponto J em derivações contíguas','j_mv',lambda v:v>=.1,'J ≥0,10 mV em duas derivações contíguas de membros; não determina infarto.',('I','II','III','aVL','aVF'),True),
        ('st_depression','Rebaixamento de ST em derivações contíguas','st60_mv',lambda v:v<=-.05,'ST em J+60 ms ≤−0,05 mV, horizontal/descendente, em duas derivações contíguas.',('I','II','III','aVL','aVF'),True),
        ('t_inversion','T invertida em derivações contíguas','t_mv',lambda v:v<=-.1,'T ≤−0,10 mV em duas derivações contíguas; não inclui aVR nem III isolada.',('I','II','III','aVL','aVF'),True),
        ('t_tall','T de amplitude elevada','t_mv',lambda v:v>.5,'T >0,50 mV em derivação de membros; descrição exploratória, sem inferência de causa.',('I','II','III','aVL','aVF'),False),
    ]:
        found = [l for l in eligible if l in valid and valid[l].get(field) is not None and predicate(valid[l][field])]
        if key=='st_depression': found=[l for l in found if valid[l]['st_slope_mv'] <= .01]
        found = contiguous(found) if paired else found
        complete = six and all(valid[l].get(field) is not None for l in eligible)
        detected = True if found else False if complete else None
        if not adult: detected=None
        add(key,label,detected,criterion,adult_reason if not adult else 'Derivações, base ou marcos insuficientes.' if detected is None else '', found,True)
    qleads = [l for l in ('I','II','aVL','aVF') if l in valid and ((valid[l]['q_ms']>=30 and valid[l]['q_mv']>=.1) or valid[l]['qs'])]
    qleads = contiguous(qleads)
    add('q_prominent','Q proeminente ou QS em derivações contíguas',bool(qleads) if adult and six else None,
        'Q inicial ≥30 ms e ≥0,10 mV, ou QS, em I/aVL ou II/aVF. Não determina etiologia nem antiguidade.',
        adult_reason if not adult else 'Derivações ou base insuficientes.' if not six else '',qleads,True)
    for key, label in [('t_biphasic','T bifásica'),('t_notched','T com entalhe'),('p_biphasic','P bifásica')]:
        found=[l for l,f in valid.items() if f.get(key)]
        complete=six and all(key in f for f in valid.values())
        add(key,label,bool(found) if complete or found else None,'Morfologia da mediana acima do ruído; descrição sem inferência de causa.',
            'Onda ou base indisponível.' if not complete and not found else '',found,True,False)
    # Sinus evidence needs available projections and reproducible P-QRS association;
    # neither regular RR nor a lone positive median P establishes sinus rhythm.
    needed=('I','II','aVR'); alignment=measurement.get('alignment',{})
    sinus=None
    if orientation_ok and all(l in valid for l in needed) and pr is not None:
        sinus=bool(valid['I']['p_mv']>.02 and valid['II']['p_mv']>.02 and valid['aVR']['p_mv']<-.02
                   and all(valid[l]['p_consistency']>=.9 and valid[l]['p_peak_dispersion_ms']<=20 and not valid[l]['p_biphasic'] for l in needed)
                   and alignment.get('accepted_beats',0)>=5 and not alignment.get('excluded')
                   and not alignment.get('unusable_segments') and not recording.gaps
                   and np.all(recording.quality[:recording.n]))
    if not orientation_ok:
        for row in rows:
            if row['amplitude_estimated']:
                row.update(status='unavailable',reason='Convenção elétrica não referenciada; selecione explicitamente o perfil empírico para usar seus pressupostos.')
    findings=[r for r in rows if r['status']=='detected']
    missing=[r for r in rows if r['required_for_normal'] and r['status']=='unavailable']
    if not findings and sinus and regular:
        summary='Sinusal, regular, normal nos critérios avaliados'
        status='no_findings'
    elif findings:
        summary='Achados na análise automática; consulte os critérios.'
        status='partial' if missing else 'findings'
    else: summary='Análise automática inconclusiva';status='inconclusive'
    return dict(version=VERSION,status=status,summary=summary,context=c,rules=rows,features=data,
        sinus_supported=sinus,regular=regular,rr_cv=cv,findings=findings,
        limitations=['Derivações de membros; sem precordiais.','Amplitudes estimadas pelo perfil ativo; hipóteses exploratórias.',
                     'Sem inferência de infarto, eletrólitos, aumento de câmaras ou bloqueio de ramo específico.'],
        missing=[r['label'] for r in missing]+([] if sinus else ['Critérios de ritmo sinusal não estabelecidos.']))
