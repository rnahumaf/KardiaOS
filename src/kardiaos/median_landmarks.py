"""Visible, bounded median smoothing and noise-aware fiducial candidates.

Only representative medians enter this module. Timing derivatives use the same
samples as the displayed curves, with no hidden Gaussian waveform smoothing.
All thresholds are exploratory engineering choices, not clinical calibration.
"""
import numpy as np
from scipy.signal import savgol_filter, find_peaks
from .qt_fiducials import endpoint

FS = 300


def smooth_median(values):
    x = np.asarray(values, float)
    candidate = savgol_filter(x, 7, 4, mode='interp')
    change = float(np.max(abs(candidate - x)))
    limit = .015 * float(np.ptp(x))
    blend = min(1., limit / change) if change else 1.
    return x + blend * (candidate - x), dict(method='Savitzky-Golay', window_samples=7,
        polynomial_order=4, blend=blend, max_sample_change_fraction=.015,
        phase='symmetric interior; polynomial edges; no causal delay', amplitude_rescaling=False)


def mad(x):
    return float(1.4826 * np.median(abs(x - np.median(x)))) if len(x) else 0.


def quiet_noise(x, anchor):
    # Estimate background outside the QRS, without fitting away ST/T morphology.
    slopes = np.r_[np.diff(x[max(0, anchor-45):anchor-24]), np.diff(x[anchor+33:min(len(x), anchor+49)])]
    return max(mad(slopes) / np.sqrt(2), np.ptp(x)*1e-5, 1e-10)


def qrs_candidate(x, anchor):
    d = np.gradient(x)
    quiet = np.r_[d[max(0, anchor-45):anchor-24], d[anchor+33:min(len(x), anchor+49)]]
    center = float(np.median(quiet)); noise = max(mad(quiet), 1e-10)
    env = abs(d-center); peak = float(max(env[anchor-18:anchor+19]))
    amplitude = float(np.ptp(x[anchor-45:anchor+46]))
    snr = peak / noise
    if snr < 6 or amplitude < 8 * quiet_noise(x, anchor):
        return {}, 'Contraste QRS insuficiente em relação ao fundo.'
    seed = anchor-18+int(np.argmax(env[anchor-18:anchor+19]))
    limits = []
    for fraction in (.06, .10):
        active = env > max(fraction*peak, 4*noise)
        left = right = seed
        lo, hi = anchor-45, anchor+46
        while left > lo+5:
            if not active[left-5:left].any(): break
            left -= 1
        while right < hi-6:
            if not active[right+1:right+6].any(): break
            right += 1
        if left <= lo+5 or right >= hi-6 or not left < anchor < right:
            return {}, 'Transição QRS não separada da janela de busca.'
        limits.append((left, right))
    sensitivity = max(abs(limits[0][j]-limits[1][j]) for j in (0, 1))
    if sensitivity > 3:
        return {}, 'Limites QRS instáveis à variação do limiar.'
    on, off = np.rint(np.mean(limits, axis=0)).astype(int)
    if not .04 <= (off-on)/FS <= .25:
        return {}, 'Duração QRS fora da faixa técnica.'
    return dict(qon=int(on), qoff=int(off), quality=float(snr),
                sensitivity_samples=int(sensitivity)), ''


def wave_candidate(x, lo, hi, kind, noise, qamp):
    """Wave feet on the visible curve; no Gaussian widening of the waveform."""
    if hi-lo < 15:
        return {}, 'Janela de onda insuficiente.'
    indices = np.arange(lo, hi)
    base = np.linspace(np.median(x[lo:lo+3]), np.median(x[hi-3:hi]), len(indices))
    local = x[lo:hi]-base
    candidates = []
    minimum = max(8*noise, (.025 if kind == 'p' else .04)*qamp)
    for sign in (1, -1):
        peaks, props = find_peaks(sign*local, prominence=minimum)
        candidates.extend((int(p), sign, float(v)) for p, v in zip(peaks, props['prominences']))
    if not candidates:
        return {}, 'Onda sem contraste suficiente na mediana.'
    peak, sign, prominence = max(candidates, key=lambda v: v[2])
    lobes = [v for v in candidates if v[2] >= .4*prominence and abs(v[0]-peak) < 45]
    if kind == 'p' and any(v[1] != sign for v in lobes):
        return {}, 'P bifásica ou sobreposta; limites ambíguos.'
    if kind == 't' and len(lobes) > 2:
        return {}, 'Morfologia T/U complexa; limite não sustentado.'
    if kind == 'p':
        # Tangents to the two main flanks avoid walking into remote baseline
        # ripple. Fits use the displayed samples, not an extra smooth waveform.
        derivative = np.gradient(local)
        lo_edge, hi_edge = max(2, peak-24), min(len(local)-3, peak+24)
        if peak-lo_edge < 3 or hi_edge-peak < 3:
            return {}, 'P sem flancos separados da borda.'
        rise = lo_edge+int(np.argmax(sign*derivative[lo_edge:peak]))
        fall = peak+int(np.argmax(-sign*derivative[peak:hi_edge]))
        fits = []
        for half in (1, 2):
            bounds = []
            for edge, direction in ((rise, sign), (fall, -sign)):
                slope, intercept = np.polyfit(np.arange(-half, half+1), local[edge-half:edge+half+1], 1)
                if direction*slope <= max(noise/3, 1e-12):
                    return {}, 'Flanco P insuficiente para delimitação.'
                bounds.append(lo+edge-intercept/slope)
            fits.append(bounds)
        if np.max(abs(np.asarray(fits[0])-fits[1])) > 3:
            return {}, 'Tangentes P instáveis.'
        on, off = np.rint(np.mean(fits, axis=0)).astype(int)
        if not lo < on < lo+peak < off < hi or not .04 <= (off-on)/FS <= .20:
            return {}, 'Tangentes P fora da onda ou da faixa técnica.'
        return dict(on=int(on), off=int(off), quality=prominence/max(noise, 1e-10),
                    sensitivity_samples=int(np.ceil(np.max(abs(np.asarray(fits[0])-fits[1]))))), ''
    first, last = min(v[0] for v in lobes), max(v[0] for v in lobes)
    limits = []
    for fraction in (.04, .08):
        threshold = max(fraction*prominence, 2*noise)
        left, right = first, last
        while left > 1 and abs(local[left]) > threshold: left -= 1
        while right < len(local)-2 and abs(local[right]) > threshold: right += 1
        if left <= 1 or right >= len(local)-2:
            return {}, 'Onda não separada da base ou da onda adjacente.'
        limits.append((lo+left, lo+right))
    sensitivity = max(abs(limits[0][j]-limits[1][j]) for j in (0, 1))
    if sensitivity > 6:
        return {}, 'Limites da onda instáveis à variação do limiar.'
    on, off = np.rint(np.mean(limits, axis=0)).astype(int)
    low, high = (.04, .20) if kind == 'p' else (.07, .40)
    if not low <= (off-on)/FS <= high:
        return {}, 'Duração da onda fora da faixa técnica.'
    return dict(on=int(on), off=int(off), quality=prominence/max(noise, 1e-10),
                sensitivity_samples=int(sensitivity)), ''


def combine_candidates(candidates, wave, on, off):
    """Keep extrema of stable, sufficiently strong projections, with audit.

    The six limb leads are dependent projections, not six independent votes.
    Do not demand a majority or average away a real terminal component. Reject
    distant weak candidates; keep a strong isolated candidate with provenance.
    """
    available = {lead: value[wave] for lead, value in candidates.items() if value.get(wave)}
    if not available: return {}, {}
    best = max(v['quality'] for v in available.values())
    selected, rejected = {}, {}
    for lead, value in available.items():
        if value['quality'] < max(8, .12*best):
            rejected[lead] = 'Contraste relativo insuficiente para definir o limite global.'
        else: selected[lead] = value
    if not selected: return {}, {}
    # Weak terminal detections far from the strong candidates are not evidence
    # of a late cardiac event. Strong unique projections remain admissible.
    strong = [v for v in selected.values() if v['quality'] >= .35*best]
    tolerance = 9 if wave == 'qrs' else 12
    for lead, value in list(selected.items()):
        if value['quality'] >= .35*best: continue
        if any(min(abs(value[k]-v[k]) for v in strong) > tolerance for k in (on, off)):
            rejected[lead] = 'Candidato isolado e de baixo contraste; não define o intervalo global.'
            del selected[lead]
    points, sources = {}, {}
    for key in (on, off):
        values = {lead: int(v[key]) for lead, v in selected.items()}
        target = min(values.values()) if key == on else max(values.values())
        points[key] = target
        sources[key] = dict(index=target, supporting_leads=[lead for lead, v in values.items() if v == target],
                            candidates=values, rejected_candidates=rejected,
                            quality={lead: float(v['quality']) for lead, v in available.items()})
    return points, sources


def delineate_medians(medians, anchor, rr):
    candidates = {}
    for lead, data in medians.items():
        qrs, why = qrs_candidate(data['qrs'], anchor)
        candidates[lead] = dict(qrs=qrs, reasons={'qrs': why})
    points, sources = combine_candidates(candidates, 'qrs', 'qon', 'qoff')
    if not points: return {}, {}, candidates
    for lead, data in medians.items():
        x = data['pt']; c = candidates[lead]
        noise = quiet_noise(x, anchor)
        amp = float(np.ptp(data['qrs'][anchor-45:anchor+46]))
        lo = max(1, anchor-105, anchor-int(.45*rr*FS))
        p, why = wave_candidate(x, lo, points['qon']-6, 'p', noise, amp)
        c['reasons']['p'] = why
        if p: c['p'] = dict(pon=p['on'], poff=p['off'], quality=p['quality'])
        hi = min(len(x)-4, anchor+180, anchor+int(rr*FS)-36)
        t, why = wave_candidate(x, points['qoff']+9, hi, 't', noise, amp)
        c['reasons']['t'] = why
        if t:
            beat = dict(r=anchor, qon=points['qon'], qoff=points['qoff'])
            end, why = endpoint(x, np.gradient(x), beat, anchor+int(rr*FS), noise, amp, 'tangent')
            if end is not None and abs(end-t['off']) <= 9 and end > t['on']:
                c['t'] = dict(ton=t['on'], toff=end, quality=t['quality'])
            else: c['reasons']['t'] = why or 'Tangente e retorno da onda à base discordam.'
    for wave, on, off in [('p', 'pon', 'poff'), ('t', 'ton', 'toff')]:
        values, provenance = combine_candidates(candidates, wave, on, off)
        points.update(values); sources.update(provenance)
    for on, off, low, high in [('pon','poff',.04,.20), ('qon','qoff',.04,.25), ('ton','toff',.07,.40)]:
        if on in points and off in points and not low <= (points[off]-points[on])/FS <= high:
            for key in (on, off): points.pop(key, None); sources.pop(key, None)
    return points, sources, candidates
