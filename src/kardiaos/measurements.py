"""Conservative, sign-invariant timing estimates from DI; no diagnostic interpretation."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks, welch
from scipy.ndimage import uniform_filter1d

from .orientation import evidence_state

FS = 300
NAMES = {'heart_rate': ('FC por RR mediano', 'bpm'), 'p_duration': ('Duração P', 'ms'),
         'qrs_duration': ('Duração QRS', 'ms'), 'qt': ('QT', 'ms'), 'qtc_f': ('QTc Fridericia', 'ms')}


def empty(reason):
    return {'status': 'unavailable', 'lead': 'I', 'method': 'template mediano; limites relativos de 5–10%, heurística v1',
            'timebase': '300 Hz nominais; relógio físico não validado',
            'calibration': 'Tempos não dependem do ganho comum positivo; mV e orientação não são validados por estas medidas.',
            'metrics': {k: dict(name=n, unit=u, value=None, status='unavailable', reason=reason) for k, (n, u) in NAMES.items()},
            'notes': ['Medições experimentais de DI, não globais de 12 derivações. Sem validação clínica.',
                      'QTcF = QT / RR^(1/3), QT em ms e RR em segundos. Não aplicado a RR muito variável, QRS largo ou limites incertos.']}


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


def stable_segment(recording, seconds=30):
    r = recording
    if r is None or not r.n or r.meta.get('start') is None: return None, 'Sem captura estabilizada.'
    if r.meta.get('sample_rate') != FS: return None, 'Frequência diferente de 300 Hz; base temporal incompatível.'
    t = r.times[:r.n]
    if not np.isfinite(t).all() or np.any(np.diff(t) <= 0): return None, 'Base temporal inválida.'
    start = int(np.searchsorted(t, r.meta['start']))
    end = int(np.searchsorted(t, r.meta.get('end') or r.last_time, side='right'))
    good = r.quality[:r.n] & (r.lead_modes[:r.n] >= 1) & ((r.raw[:r.n, 0] & 3) == 0)
    good[:start] = False; good[end:] = False
    breaks = np.flatnonzero(~np.isclose(np.diff(t), 1 / FS, rtol=0, atol=1e-6)) + 1
    cuts = sorted(set([0, r.n, *breaks.tolist(), *(np.flatnonzero(np.diff(good.astype(int)))+1).tolist()]))
    segments = [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a and good[a] and good[a:b].all()]
    if not segments: return None, 'Sem trecho contínuo com contato aceito em DI.'
    a, b = max(segments, key=lambda ab: (ab[1] - ab[0], -ab[0]))
    if b - a < 10 * FS: return None, 'São necessários pelo menos 10 s contínuos com contato aceito.'
    return (a, min(b, a + seconds * FS)), None


def _boundaries(template, lo, hi, peak, noise, width_limits, quiet=3):
    region = np.abs(template[lo:hi])
    amplitude = float(abs(template[peak]))
    if amplitude < max(8 * noise, 1e-8): return None, 'Onda sem separação suficiente do ruído.'
    bounds = []
    for fraction in (.05, .10):
        threshold = max(3 * noise, fraction * amplitude)
        above = np.abs(template) > threshold
        left = right = None
        for j in range(peak - quiet, lo - 1, -1):
            if not above[j:j + quiet].any(): left = j + quiet; break
        for j in range(peak + 1, hi - quiet + 1):
            if not above[j:j + quiet].any(): right = j; break
        if left is None or right is None: return None, 'Limite de onda não separado da borda/onda adjacente.'
        width = (right - left) / FS * 1000
        if not width_limits[0] <= width <= width_limits[1]: return None, 'Duração fora dos limites deste delineador experimental.'
        bounds.append((left, right))
    if max(abs(bounds[0][j] - bounds[1][j]) for j in (0, 1)) / FS > .020:
        return None, 'Limites instáveis ao variar o limiar de delineação.'
    return tuple(int(round(np.mean([v[j] for v in bounds]))) for j in (0, 1)), None


def measure_recording(recording):
    result = empty('Limites de onda ainda não determinados.')
    segment, error = stable_segment(recording)
    if error: return empty(error)
    a, b = segment
    result.update(first_sample=a, last_sample_exclusive=b,
                  offset_seconds=float(recording.times[a] - recording.meta['start']), duration_seconds=(b-a)/FS,
                  synthetic=bool(recording.meta.get('synthetic')), amplitude_verified=evidence_state(recording)['amplitude']['I'])
    raw = recording.raw[a:b, 0].astype(float)
    error = technical_quality(raw)
    if error:
        for m in result['metrics'].values(): m['reason'] = error
        return result
    def unavailable(keys, why):
        for key in keys: result['metrics'][key].update(value=None, status='unavailable', reason=why)
    def value(key, val, **extra):
        result['metrics'][key].update(value=round(float(val), 1), status='experimental', reason='', **extra)
    x = sosfiltfilt(butter(3, [.5, 40], btype='bandpass', fs=FS, output='sos'), raw)
    band = sosfiltfilt(butter(3, [5, 25], btype='bandpass', fs=FS, output='sos'), raw)
    energy = uniform_filter1d(np.gradient(band) ** 2, size=24)
    candidates = []
    for fraction in (.12, .25):
        peaks, _ = find_peaks(energy, distance=int(.28*FS), prominence=fraction*np.percentile(energy, 99))
        refined = []
        for p in peaks:
            if p < .4*FS or p >= len(x)-.6*FS: continue
            q = p-24+int(np.argmax(abs(x[p-24:p+25])))
            if q < 105 or q + 166 > len(x): continue
            if not refined or q-refined[-1] >= .25*FS: refined.append(q)
        candidates.append(np.array(refined, dtype=int))
    peaks, other = candidates
    if len(peaks) < 5 or len(peaks) != len(other) or np.max(abs(peaks-other)) > .03*FS:
        unavailable(NAMES, 'Poucos QRS candidatos ou detecção instável; não há base suficiente para medir.')
        return result
    rr = np.diff(peaks) / FS
    if np.any((rr < .3) | (rr > 2.0)):
        unavailable(NAMES, 'Intervalos candidatos fora da faixa técnica; possível detecção incorreta.')
        return result
    # Reject low-contrast/noise detections before offering even a rate.
    beats = np.stack([x[p-105:p+166] for p in peaks])
    beats -= np.median(beats[:, :20], axis=1)[:, None]
    template = np.median(beats, axis=0)
    centered = beats-beats.mean(axis=1)[:,None]
    tc = template-template.mean()
    correlations = (centered @ tc) / np.maximum(np.linalg.norm(centered,axis=1)*np.linalg.norm(tc),1e-20)
    residual = beats-template
    noise = float(np.median(abs(residual-np.median(residual))) * 1.4826)
    if np.median(correlations) < .80 or np.max(abs(template)) < 8*max(noise,1e-8):
        unavailable(NAMES, 'QRS candidatos sem repetibilidade/separação do ruído suficiente.')
        return result
    value('heart_rate', 60/np.median(rr), rr_median_seconds=float(np.median(rr)), beats=len(peaks))
    result.update(status='experimental', beats=len(peaks), rr_variability=float(np.std(rr)/np.mean(rr)))
    if np.median(correlations) < .92 or result['rr_variability'] > .10:
        unavailable(['p_duration','qrs_duration','qt','qtc_f'], 'Morfologia/RR variável; template não sustenta delineação estável.')
        return result
    # Baseline is estimated outside P/QRS/T; absolute amplitudes make timing sign invariant.
    template -= float(np.median(template[:15]))
    center = 105
    qpeak = center-18+int(np.argmax(abs(template[center-18:center+19])))
    qrs, why = _boundaries(template, center-42, center+45, qpeak, noise, (40,200))
    if qrs is None:
        unavailable(['p_duration','qrs_duration','qt','qtc_f'], why)
        return result
    qon, qoff = qrs
    value('qrs_duration', (qoff-qon)/FS*1000)
    p_lo, p_hi = 6, qon-12
    if p_hi-p_lo < 15:
        unavailable(['p_duration'], 'Janela P sem separação do QRS.')
    else:
        ppeak = p_lo+int(np.argmax(abs(template[p_lo:p_hi])))
        p, why = _boundaries(template,p_lo,p_hi,ppeak,noise,(40,200))
        if p is None: unavailable(['p_duration'],why)
        else: value('p_duration',(p[1]-p[0])/FS*1000)
    t_lo, t_hi = qoff+15, min(len(template)-4, center+int(min(.52,.65*np.median(rr))*FS))
    if t_hi-t_lo < 30:
        unavailable(['qt','qtc_f'],'Janela T insuficiente ou sobreposta ao ciclo seguinte.')
        return result
    tpeak = t_lo+int(np.argmax(abs(template[t_lo:t_hi])))
    t, why = _boundaries(template,t_lo,t_hi,tpeak,noise,(60,350))
    if t is None:
        unavailable(['qt','qtc_f'],why)
        return result
    qt = (t[1]-qon)/FS*1000
    if not 200 <= qt <= 600:
        unavailable(['qt','qtc_f'],'QT fora dos limites técnicos de delineação.')
        return result
    value('qt',qt)
    if result['metrics']['qrs_duration']['value'] >= 120 or not .6 <= np.median(rr) <= 1.5:
        unavailable(['qtc_f'],'QTc não aplicado: QRS >=120 ms ou RR fora de 0,6–1,5 s; requer avaliação específica.')
    else: value('qtc_f',qt/np.cbrt(np.median(rr)),formula='QTcF = QT(ms) / RR(s)^(1/3)')
    result['fiducials_template_samples'] = dict(qrs_onset=qon,qrs_offset=qoff,t_offset=t[1],r_anchor=center)
    return result
