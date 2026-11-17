"""Auditable, exploratory rules on synchronized medians and original RR.

Thresholds and limitations are documented in docs/rules-0100.md. Missing data
never counts as a negative rule. No diagnosis of infarction or chamber disease.
"""
import numpy as np
from .median_landmarks import mad
from .orientation import normal_signs
from .morphology_rules import describe_wave
from .signal import FS

VERSION = 'limb-rules-8'
MIN_RHYTHM_COVERAGE = .90
MAX_RHYTHM_GAP_SECONDS = 2.
MIN_CONTINUOUS_RHYTHM_SECONDS = 10
GROUPS = [('I', 'aVL'), ('II', 'III', 'aVF')]
DESCRIPTIONS = ('p_biphasic', 't_biphasic', 't_notched')


def context(recording):
    value = recording.meta.get('clinical_context', {}) if recording else {}
    if not isinstance(value, dict): value = {}
    age = value.get('age_years'); sex = value.get('sex')
    if isinstance(age, bool) or not isinstance(age, (int, float)) or not np.isfinite(age) or not 0 <= age <= 120: age = None
    if sex not in ('male', 'female'): sex = None
    return dict(age_years=age, sex=sex)


def contiguous(leads):
    return sorted(set().union(*(set(leads).intersection(g) for g in GROUPS if len(set(leads).intersection(g)) >= 2)))


def rhythm_quality(recording, measurement):
    alignment = measurement.get('alignment', {})
    coverage = alignment.get('rhythm', {}).get('coverage')
    if coverage is not None:
        return coverage['fraction'] >= MIN_RHYTHM_COVERAGE and coverage['longest_gap_seconds'] <= MAX_RHYTHM_GAP_SECONDS
    if alignment.get('unusable_segments'):
        return False
    if 'first_sample' not in measurement or 'last_sample_exclusive' not in measurement:
        return bool(not recording.gaps and np.all(recording.quality[:recording.n]))
    first, last = measurement['first_sample'], measurement['last_sample_exclusive']
    time = recording.times[first:last]
    quality = recording.quality[first:last]
    return bool(len(time) and np.all(quality) and np.allclose(np.diff(time), 1/300, atol=1e-6, rtol=0))


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
        p_shape = describe_wave(p, noise, 'p')['biphasic']
        f['p_biphasic'] = p_shape['status'] == 'detected'
        f['p_biphasic_possible'] = p_shape['status'] == 'possible'
        f['morphology'] = {'p_biphasic':dict(p_shape, start_index=points['pon'])}
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
        f['q_indices'] = (negative+points['qon']).tolist()
        f['qs'] = bool(not len(positive) and f['q_mv'] > threshold)
        j = points['qoff']
        f['j_mv'] = float(np.mean(q[j-1:j+2])-qb)
        f['st60_mv'] = float(np.mean(q[j+17:j+20])-qb) if j+20 < points.get('ton', j) else None
        f['st_slope_mv'] = f['st60_mv']-float(np.mean(q[j+5:j+8])-qb) if f['st60_mv'] is not None else None
        if all(k in points for k in ('ton', 'toff')) and points['toff'] > points['ton']:
            t = pt[points['ton']:points['toff']+1]-pb
            f['t_mv'] = float(t[np.argmax(abs(t))]); f['t_duration_ms'] = (points['toff']-points['ton'])/.3
            t_shape = describe_wave(t, noise, 't')
            for key,shape in [('t_biphasic',t_shape['biphasic']),('t_notched',t_shape['notched'])]:
                f[key] = shape['status'] == 'detected'
                f[key+'_possible'] = shape['status'] == 'possible'
                f['morphology'][key] = dict(shape, start_index=points['ton'])
        else: f['t_mv'] = None
    return result


def classify(recording, measurement, representatives, *, feature_data=None, check_stability=True):
    c = context(recording); adult = c['age_years'] is not None and c['age_years'] >= 18
    amplitude_eligible = adult or c['age_years'] is None
    adult = amplitude_eligible
    data = features(measurement, representatives) if feature_data is None else feature_data; rows = []
    metrics = measurement.get('metrics', {})
    def metric(key): return metrics.get(key, {}).get('value')
    def add(key, label, detected, criterion, reason='', leads=(), amplitude=False, required=True):
        status = 'unavailable' if detected is None else 'detected' if detected else 'not_detected'
        rows.append(dict(id=key, label=label, status=status, criterion=criterion, reason=reason,
                         leads=list(leads), amplitude_estimated=amplitude, required_for_normal=required,
                         presentation='description' if key in DESCRIPTIONS else 'finding', limitations=[]))
    adult_reason = 'Faixa pediátrica sem regras validadas para estes limiares de adulto.'
    hr, pr, qrs, pd, qtc = (metric(k) for k in ('heart_rate','pr','qrs_duration','p_duration','qtc_f'))
    alignment = measurement.get('alignment', {})
    rhythm = alignment.get('rhythm', {})
    premature = rhythm.get('premature')
    events = premature.get('events', []) if premature else []
    rr = np.asarray(rhythm.get('rr_seconds', []))
    rhythm_ok = len(rr) >= 4 and np.all((rr >= .25) & (rr <= 3))
    cv = float(np.std(rr)/np.mean(rr)) if rhythm_ok else None
    regular = bool(cv <= .10 and np.max(abs(rr-np.median(rr)))/np.median(rr) <= .15) if cv is not None else None
    add('irregular', 'Ritmo irregular', None if regular is None else not regular,
        'CV dos RR >10% ou desvio máximo da mediana >15%; limiares exploratórios, sem diagnóstico de fibrilação atrial.', 'RR insuficientes.' if regular is None else '')
    if premature is not None:
        count = len(events)
        label = f'{count} batimento prematuro de QRS distinto' if count == 1 else (
            f'{count} batimentos prematuros de QRS distinto' if count else 'Batimentos prematuros de QRS distinto')
        assessed = premature['evaluated'] and not premature['unresolved']
        add('premature', label, True if events else False if assessed else None,
            'QRS distinto e RR anterior abaixo de 80% da referência local. Forma, largura e pausa ajudam a estimar a origem.',
            '' if events or assessed else 'Sem sequência local suficiente para caracterizar os complexos distintos.',
            required=False)
        ventricular = sum(e['ventricular_pattern'] for e in events)
        if ventricular:
            suffix = 'complexo compatível com extrassístole ventricular' if ventricular == 1 else 'complexos compatíveis com extrassístoles ventriculares'
            rows[-1]['interpretation'] = f'{ventricular} {suffix}.'
    for key, label, condition, criteria in [
        ('brady','Bradicardia',hr is not None and hr < 60,'FC <60 bpm em adulto.'),
        ('tachy','Taquicardia',hr is not None and hr > 100,'FC >100 bpm em adulto.'),
        ('pr_long','PR prolongado; possível atraso de condução AV',pr is not None and pr > 200,'PR global >200 ms em adulto; não determina o mecanismo.'),
        ('pr_short','PR curto',pr is not None and pr < 120,'PR global <120 ms em adulto; não diagnostica pré-excitação.'),
        ('qrs_wide','QRS alargado',qrs is not None and qrs >= 120,'QRS global ≥120 ms em adulto; sem identificação de ramo.'),
        ('p_wide','P alargada; possível atraso de condução atrial',pd is not None and pd >= 120,'P global ≥120 ms em adulto; sem diagnóstico de aumento atrial.')]:
        value = hr if key in ('brady','tachy') else pr if key.startswith('pr_') else qrs if key=='qrs_wide' else pd
        quality = metrics.get('pr', {}).get('quality', {})
        borderline = (key == 'pr_short' and adult and condition and 0 < 120-pr <= 1000/FS
                      and quality.get('status') in ('review', 'unverified'))
        add(key,'PR limítrofe' if borderline else label,bool(condition and not borderline) if adult and value is not None else None,criteria,
            adult_reason if not adult else 'Limites necessários indisponíveis.' if value is None else '')
        if borderline:
            duration = f'{pr:g}'.replace('.', ',')
            warning = quality.get('reason') or 'Estabilidade do PR não confirmada.'
            rows[-1]['possible_context'] = f'PR limítrofe de {duration} ms, a até uma amostra de 120 ms. {warning}'
    qt_limit = 450 if c['sex']=='male' else 460
    qt_reason = ''
    if not adult: qt_reason = adult_reason
    elif qtc is None: qt_reason = metrics.get('qtc_f',{}).get('reason') or 'QTcF indisponível.'

    add('qt_long','QTcF prolongado',qtc >= qt_limit if adult and qtc is not None else None,
        'QTcF ≥450 ms (masculino) ou ≥460 ms (feminino), adulto; condições de RR/QRS da medição mantidas.',
        qt_reason)
    if adult and qtc is not None and not c['sex']:
        rows[-1]['limitations'].append('Sexo não informado: comparação com os limiares masculino (450 ms) e feminino (460 ms).')
        if 450 <= qtc < 460:
            rows[-1]['possible_context'] = 'Possível prolongamento, dependente do sexo de referência; não altera sozinho a conclusão principal.'
    valid = {l:f for l,f in data.items() if f['available']}
    six = all(l in valid for l in ('I','II','III','aVR','aVL','aVF'))
    only_di = set(data) == {'I'}
    orientation_ok = normal_signs(recording, 'ecgfounder_1l' if only_di else 'deeppsp_2l') is not None
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
        if not amplitude_eligible: detected=None
        add(key,label,detected,criterion,adult_reason if not amplitude_eligible else 'Derivações, base ou marcos insuficientes.' if detected is None else '', found,True)
    qleads = [l for l in ('I','II','aVL','aVF') if l in valid and ((valid[l]['q_ms']>=30 and valid[l]['q_mv']>=.1) or valid[l]['qs'])]
    qleads = contiguous(qleads)
    add('q_prominent','Q proeminente ou QS em derivações contíguas',bool(qleads) if amplitude_eligible and (six or qleads) else None,
        'Q inicial ≥30 ms e ≥0,10 mV, ou QS, em I/aVL ou II/aVF. Não determina etiologia nem antiguidade.',
        adult_reason if not amplitude_eligible else 'Derivações ou base insuficientes.' if not six and not qleads else '',qleads,True)
    for key, label in [('t_biphasic','T bifásica'),('t_notched','T com entalhe'),('p_biphasic','P bifásica')]:
        found=[l for l,f in valid.items() if f.get(key)]
        complete=bool(valid) and all(key in f for f in valid.values())
        add(key,label,bool(found) if complete or found else None,'Morfologia da mediana acima do ruído; descrição sem inferência de causa.',
            'Onda ou base indisponível.' if not complete and not found else '',found,True,False)
        possible = [l for l,f in valid.items() if f.get(key+'_possible')]
        if possible: rows[-1]['possible_morphology_leads'] = possible
    # Check conducted beats for the origin of the prevailing rhythm. Detected
    # premature complexes remain part of the sequence used for RR and rate.
    needed = ('I',) if only_di else ('I', 'II', 'aVR')
    sinus_label = 'Ritmo compatível com sinusal em DI' if only_di else 'Ritmo de base sinusal'
    association = rhythm.get('p_association')
    sinus_reasons=[]
    for lead in needed:
        if lead not in valid:sinus_reasons.append(lead+': P/base indisponível');continue
        f=valid[lead]
        if (f['p_mv']<=.02 if lead!='aVR' else f['p_mv']>=-.02):sinus_reasons.append(lead+': polaridade/amplitude de P fora do critério')
        if association is None and not only_di:
            if f['p_consistency']<.9:sinus_reasons.append(f"{lead}: P consistente em {f['p_consistency']:.0%} dos batimentos (mínimo 90%)")
            if f['p_peak_dispersion_ms']>20:sinus_reasons.append(f"{lead}: dispersão de P {f['p_peak_dispersion_ms']:.1f} ms (limite 20 ms)")
    if association is None and only_di:
        sinus_reasons.append('Associação P–QRS em DI indisponível')
    elif association is not None and not association['supported']:
        if association['fraction'] < .9:
            sinus_reasons.append(f"Associação P–QRS em {association['matched']}/{association['evaluated']} batimentos predominantes (mínimo de 90%)")
        elif association['dispersion_ms'] is None or association['dispersion_ms'] > 20:
            sinus_reasons.append('Dispersão da associação P–QRS acima do limite técnico de 20 ms')
        else:
            sinus_reasons.append('Associação P–QRS diverge entre trechos válidos')
    if pr is None:sinus_reasons.append('PR indisponível')
    if alignment.get('accepted_beats',0)<5:sinus_reasons.append('Menos de cinco batimentos aceitos')
    identified = {event['sample'] for event in events}
    unexplained = sum(item['sample'] not in identified for item in alignment.get('excluded', []))
    if unexplained:
        sinus_reasons.append(f'{unexplained} batimento(s) de morfologia distinta ainda sem caracterização')
    usable_rhythm = rhythm_quality(recording, measurement)
    coverage = rhythm.get('coverage')
    supported_starts = {group['first_sample'] for group in (association or {}).get('segments', [])
                        if group['supported']}
    # A limited conclusion still requires concordant P–QRS and RR evidence,
    # including a continuous segment with enough individually matched beats.
    limited_rhythm = (not usable_rhythm and not sinus_reasons and regular is True and not events
                      and coverage is not None and any(
                          first in supported_starts and last-first >= MIN_CONTINUOUS_RHYTHM_SECONDS*FS
                          for first, last in coverage.get('segments', [])))
    if limited_rhythm:
        derivation = ' em DI' if only_di else ''
        sinus_label = f'Ritmo regular compatível com sinusal{derivation} nos trechos válidos'
    elif not usable_rhythm:
        sinus_reasons.append('Trechos sem qualidade/continuidade suficiente na janela analisada')
    sinus = not sinus_reasons if all(l in valid for l in needed) and pr is not None else None
    sinus_limitations = [] if orientation_ok else ['Ritmo avaliado assumindo a polaridade exibida, sem referência validada.']
    if coverage and coverage['longest_gap_seconds'] > 1/FS:
        sinus_limitations.append(f"Ritmo avaliado nos trechos válidos: {coverage['seconds']:.1f} de {coverage['duration_seconds']:.1f} s. "
                                 f"Maior perda de sinal ou de continuidade: {coverage['longest_gap_seconds']:.2f} s.")
    for row in rows:
        if c['age_years'] is None and row['id'] not in ('irregular','premature',*DESCRIPTIONS):
            row['limitations'].append('Idade não informada: comparação exploratória com limiares de adulto.')
        if not row['amplitude_estimated']: continue
        row['limitations'].append('Amplitude estimada pelo perfil ativo; calibração não validada.')
        if not orientation_ok:
            row['limitations'].append('Convenção elétrica não referenciada: polaridade do traçado exibido assumida para esta comparação exploratória.')
    if check_stability:
        from .measurement_quality import guard_rules
        guard_rules(recording,measurement,rows)
    findings=[r for r in rows if r['status']=='detected' and r['presentation']=='finding']
    missing=[r for r in rows if r['required_for_normal'] and r['status']=='unavailable']
    if limited_rhythm:
        summary=sinus_label
        status='partial'
    elif only_di and sinus and regular:
        summary='Ritmo regular compatível com sinusal em DI'
        status=('partial' if missing else 'findings') if findings else 'no_findings'
    elif not findings and sinus and regular:
        summary='Sinusal, regular, normal nos critérios avaliados'
        status='no_findings'
    elif findings:
        if sinus and (events or regular is False):
            parts = [sinus_label]
            if events:
                parts.append(f'{len(events)} batimento prematuro' if len(events) == 1 else f'{len(events)} batimentos prematuros')
            if regular is False:
                parts.append('RR irregular')
            summary = ', '.join(parts[:-1]) + ' e ' + parts[-1]
        else:
            summary='Achados na análise automática; consulte os critérios.'
        status='partial' if missing else 'findings'
    else: summary='Análise automática inconclusiva';status='inconclusive'
    return dict(version=VERSION,status=status,summary=summary,context=c,rules=rows,features=data,
        morphology=[r for r in rows if r['presentation']=='description'],
        possibilities=[r for r in rows if r.get('possible') and r['presentation']=='finding'],
        sinus_reasons=sinus_reasons,p_association=association,sinus_label=sinus_label,
        sinus_limitations=sinus_limitations,sinus_leads=list(needed),
        sinus_supported=sinus,regular=regular,rr_cv=cv,findings=findings,
        limitations=['Derivações de membros; sem precordiais.','Amplitudes estimadas pelo perfil ativo; hipóteses exploratórias.',
                     'Sem inferência de infarto, eletrólitos, aumento de câmaras ou bloqueio de ramo específico.'],
        missing=[r['label'] for r in missing]+([] if sinus else ['Critérios de ritmo sinusal não estabelecidos: '+'; '.join(sinus_reasons)+'.']))
