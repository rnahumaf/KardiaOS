"""Whole-record synchronized median beats and global limb-lead intervals.

One QRS clock, one translation and one morphology decision per beat. No temporal
warping, per-beat amplitude normalization, individual-beat delineation or neural
endpoint fallback. This exploratory method has no clinical qualification.
"""
from copy import deepcopy
import numpy as np
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
from scipy.signal import butter, sosfiltfilt, find_peaks, welch
from . import delineation as dsp
from .qt_fiducials import t_filter
from .median_landmarks import smooth_median, delineate_medians
from .processing import scale_and_signs
from .signal import six_leads
from .measurement_engine import empty
from .rhythm_analysis import analyze_premature, p_association, similarity

FS = 300
VERSION = 'global-median-6'
LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF']
METHOD = 'Limites globais nas medianas alinhadas da gravação completa'


def qtc_blockers(qt, qrs, rr):
    """Explain the existing QTc eligibility policy without relaxing its gates."""
    rr = np.asarray(rr, dtype=float)
    reasons = []
    if qt is None: reasons.append('QT indisponível: limites globais insuficientes.')
    if qrs is None: reasons.append('Duração do QRS indisponível.')
    elif qrs >= 120:
        reasons.append(f'QRS de {qrs:g} ms, fora da condição de QRS menor que 120 ms.')
    if len(rr) < 4: reasons.append(f'RR insuficientes: {len(rr)} intervalos; mínimo de 4.')
    if len(rr):
        median = float(np.median(rr)); mean = float(np.mean(rr))
        if not .6 <= median <= 1.5:
            reasons.append(f'RR mediano de {median*1000:.1f} ms, fora da faixa de 600–1500 ms.')
        cv = float(np.std(rr)/mean) if mean > 0 else float('inf')
        if not np.isfinite(cv): reasons.append('Variabilidade dos RR não calculável.')
        elif cv > .1:
            value = f'{cv*100:.2f}'.replace('.', ',')
            reasons.append(f'Variabilidade dos RR de {value}%, acima do limite de 10%.')
    return reasons


def joint_quality(raw):
    """Gross acquisition checks jointly; a flat projection cannot veto another."""
    x = np.asarray(raw, float)
    if len(x) < 2 * FS or not np.isfinite(x).all():
        return False
    if np.max(np.std(x, axis=0)) < 3 or np.any(abs(x) >= 32760):
        return False
    f, power = welch(x, fs=FS, nperseg=min(900, len(x)), axis=0)
    useful = power[(f >= 5) & (f <= 40)].sum()
    high = power[f >= 45].sum()
    return bool(high / max(useful, 1e-20) <= .5)


def segments(recording, channels):
    """Never join transport gaps, contact loss or unavailable native channels."""
    r = recording
    t = r.times[:r.n]
    good = (r.quality[:r.n] & (r.lead_modes[:r.n] >= (6 if channels == 2 else 1))
            & np.all((r.raw[:r.n, :channels] & 3) == 0, axis=1)
            & np.all(np.abs(r.raw[:r.n, :channels].astype(float)) < 32760, axis=1))
    good &= (t >= float(r.meta['start']) - 1e-7) & (t <= float(r.meta.get('end') or r.last_time) + 1e-7)
    cuts = sorted(set([0, r.n, *list(np.flatnonzero(np.diff(good.astype(int))) + 1),
                       *list(np.flatnonzero(~np.isclose(np.diff(t), 1 / FS, atol=1e-6, rtol=0)) + 1)]))
    return [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if good[a] and b - a >= 2 * FS]


def shared_peaks(raw):
    """Joint native-channel QRS energy; derived low-voltage leads cannot veto it."""
    x = sosfiltfilt(butter(3, [3, 25], btype='bandpass', fs=FS, output='sos'), raw, axis=0)
    energy = uniform_filter1d(np.sum(np.gradient(x, axis=0) ** 2, axis=1), 24)
    scale = float(np.percentile(energy, 99))
    if scale <= 1e-12:
        return np.array([], dtype=int), x
    candidates, _ = find_peaks(energy, distance=84, prominence=.12 * scale)
    magnitude = np.sum(x ** 2, axis=1)
    peaks = []
    for p in candidates:
        if p < 30 or p + 30 >= len(x):
            continue
        q = int(p - 24 + np.argmax(magnitude[p - 24:p + 25]))
        if not peaks or q - peaks[-1] >= 75:
            peaks.append(q)
    return np.asarray(peaks, dtype=int), x


def align_beats(candidates):
    """Robust shared translation, then conservative exclusion of distinct QRS.

    Channel amplitudes only weight the joint comparison; all output curves keep
    their recorded amplitude. RR never participates in morphology rejection.
    """
    if not candidates:
        return [], []
    reference = np.median([c['align'][c['p'] - 45:c['p'] + 46] for c in candidates], axis=0)
    for _ in range(3):
        for c in candidates:
            p, x = c['p'], c['align']
            score, _, shift = max((similarity(x[p + lag - 45:p + lag + 46], reference), -abs(lag), lag)
                                  for lag in range(-12, 13))
            c.update(shift=shift, correlation=score)
        scores = np.array([c['correlation'] for c in candidates])
        seed = [c for c in candidates if c['correlation'] >= max(.75, np.median(scores) - .12)]
        if not seed:
            seed = candidates
        reference = np.median([c['align'][c['p'] + c['shift'] - 45:c['p'] + c['shift'] + 46] for c in seed], axis=0)
    reference = reference - reference.mean(axis=0)
    norm = max(float(np.linalg.norm(reference)), 1e-12)
    residuals = []
    for c in candidates:
        p = c['p'] + c['shift']
        curve = c['align'][p - 45:p + 46]
        curve = curve - curve.mean(axis=0)
        c['correlation'] = similarity(curve, reference)
        c['residual'] = float(np.linalg.norm(curve - reference) / norm)
        residuals.append(c['residual'])
    median = float(np.median(residuals))
    mad = float(np.median(abs(np.asarray(residuals) - median))) * 1.4826
    cutoff = max(.65, median + 6 * mad)
    accepted, rejected = [], []
    for c in candidates:
        if c['correlation'] < .80 or c['residual'] > cutoff:
            rejected.append(dict(sample=c['absolute'], wave='qrs', reason='Morfologia QRS distinta do conjunto predominante nas entradas simultâneas.',
                                 correlation=c['correlation'], relative_residual=c['residual'], scope='all_leads'))
        else:
            accepted.append(c)
    # A clearly distinct P/T morphology also excludes the entire simultaneous
    # beat. Comparison is multichannel and noise-relative, never an RR grouping.
    for wave, left, right in [('P', -100, -30), ('T', 36, 170)]:
        if len(accepted) < 5:
            break
        # At short adjacent RR the comparison window can contain a different
        # beat's T/P. Such a window is not evidence of distinct morphology.
        comparable = [c for c in accepted if c['previous_rr' if wave == 'P' else 'next_rr'] >= .8]
        if len(comparable) < 5:
            continue
        curves = []
        for c in comparable:
            p = c['p'] + c['shift']
            curve = c['pt'][p + left:p + right, :c['align'].shape[1]]
            baseline = np.linspace(curve[:3].mean(axis=0), curve[-3:].mean(axis=0), len(curve))
            curves.append(curve - baseline)
        reference = np.median(curves, axis=0)
        norm = np.linalg.norm(reference)
        # No dominant wave: preserve curves; the median delineator must abstain.
        if norm < 1e-8:
            continue
        residuals = np.array([np.linalg.norm(curve - reference) / norm for curve in curves])
        center = np.median(residuals); mad = 1.4826 * np.median(abs(residuals - center))
        cutoff = max(1.2, center + 6 * mad)
        removed = set()
        for c, curve, residual in zip(comparable, curves, residuals):
            noise = np.linalg.norm(curve - gaussian_filter1d(curve, 2, axis=0))
            if residual > cutoff and norm > 6 * max(noise, 1e-8):
                rejected.append(dict(sample=c['absolute'], wave=wave.lower(), reason=f'Morfologia de {wave} distinta do conjunto predominante nas entradas simultâneas.',
                                     relative_residual=float(residual), scope='all_leads'))
                removed.add(c['absolute'])
        accepted = [c for c in accepted if c['absolute'] not in removed]
    return accepted, rejected


def global_boundaries(medians, anchor, rr):
    return delineate_medians(medians, anchor, rr)


def analyze(recording, cancelled=lambda: False):
    from .automatic_analysis import Cancelled
    r = recording
    channels = 2 if np.any(r.lead_modes[:r.n] == 6) else 1
    names = LEADS if channels == 2 else ['I']
    factor, signs = scale_and_signs(r)
    candidates, peaks_all, rr_all, incomplete, unusable = [], [], [], [], []
    rr_pairs = []
    # Fixed shared crop; shifts never stretch P, QRS, T or an RR interval.
    pre, post = 105, 180
    for a, b in segments(r, channels):
        if cancelled(): raise Cancelled()
        native = r.raw[a:b, :channels].astype(float) * np.asarray(signs[:channels])
        if not joint_quality(native):
            unusable.append(dict(first_sample=a,last_sample_exclusive=b,reason='Segmento sem sinal variável suficiente ou com ruído de alta frequência excessivo.'))
            continue
        peaks, align = shared_peaks(native)
        peaks_all.extend((peaks + a).tolist())
        rr_all.extend((np.diff(peaks) / FS).tolist())
        rr_pairs.extend([[int(x+a),int(y+a)] for x,y in zip(peaks[:-1],peaks[1:])])
        raw = six_leads(native) if channels == 2 else native
        qrs = np.column_stack([dsp.preprocess(raw[:, ch]) for ch in range(len(names))])
        pt = np.column_stack([t_filter(raw[:, ch]) for ch in range(len(names))])
        for index, p in enumerate(peaks):
            if p - pre - 12 < 0 or p + post + 12 >= b - a:
                incomplete.append(dict(sample=int(a + p), reason='Janela incompleta na borda de um segmento contínuo.', scope='all_leads'))
                continue
            candidates.append(dict(p=int(p), absolute=int(a + p), start=a, align=align, raw=raw, qrs=qrs, pt=pt,
                                   previous_rr=float((p - peaks[index - 1]) / FS) if index else float('inf'),
                                   next_rr=float((peaks[index + 1] - p) / FS) if index + 1 < len(peaks) else float('inf')))
    accepted, excluded = align_beats(candidates)
    # A 6L morphology set may coexist with valid I-only portions. Keep those
    # original beats in rhythm without manufacturing RR across missing contact.
    if channels == 2:
        peaks_all, rr_all, rr_pairs = [], [], []
        for a, b in segments(r, 1):
            if cancelled(): raise Cancelled()
            cuts = [a, *list(a + np.flatnonzero(np.diff((r.lead_modes[a:b] == 6).astype(int))) + 1), b]
            for lo, hi in zip(cuts[:-1], cuts[1:]):
                if hi - lo < 2 * FS: continue
                count = 2 if np.all(r.lead_modes[lo:hi] == 6) and np.all((r.raw[lo:hi, 1] & 3) == 0) and np.all(abs(r.raw[lo:hi,1].astype(float))<32760) else 1
                native = r.raw[lo:hi, :count].astype(float) * np.asarray(signs[:count])
                if not joint_quality(native): continue
                peaks, _ = shared_peaks(native)
                peaks_all.extend((peaks + lo).tolist()); rr_all.extend((np.diff(peaks) / FS).tolist())
                rr_pairs.extend([[int(x+lo),int(y+lo)] for x,y in zip(peaks[:-1],peaks[1:])])
    rr = np.asarray(rr_all, dtype=float)
    median_rr = float(np.median(rr)) if len(rr) else None
    rhythm = dict(detected_peaks=peaks_all, rr_seconds=rr_all, rr_pairs=rr_pairs, method='RR originais, inclusive batimentos excluídos da mediana; sem atravessar lacunas')
    audit = dict(version=VERSION, scope='whole_recording', channels=names, detected_beats=len(peaks_all),
                 accepted_beats=len(accepted), excluded=excluded, incomplete=incomplete, unusable_segments=unusable,
                 exclusions_scope='all_leads', maximum_shift_samples=12,
                 source_centers=[c['absolute'] + c['shift'] for c in accepted],
                 original_peaks=[c['absolute'] for c in accepted], translation_samples=[c['shift'] for c in accepted],
                 rhythm=rhythm, clinical_validation=False)
    result = empty('Mediana sem batimentos completos suficientes.')
    result.update(method=METHOD, method_version=VERSION, global_intervals=True, lead='I',
                  first_sample=int(np.searchsorted(r.times[:r.n], float(r.meta['start']) - 1e-7)),
                  last_sample_exclusive=int(np.searchsorted(r.times[:r.n], float(r.meta.get('end') or r.last_time) + 1e-7)),
                  offset_seconds=0., duration_seconds=float((r.meta.get('end') or r.last_time) - r.meta['start']),
                  detected_peaks=peaks_all, fiducials=[], candidate_beats=len(candidates), beats=len(accepted),
                  pipeline=dict(id=VERSION, source='aligned_medians_only', sample_rate_hz=FS, highpass_hz=.5,
                                lowpass_hz=80, pt_lowpass_hz=30, phase='zero', neural_endpoints=False, t_onset='ST/rising-limb change point', t_offset='baseline band return',
                                median_smoothing='bounded Savitzky-Golay 7/4', detector_source='displayed_smoothed_medians'),
                  notes=['Intervalos globais das derivações de membros disponíveis; sem precordiais.',
                         'FC e RR usam a sequência original completa; limites usam somente medianas.'],
                  alignment=audit, additional_leads=[])
    metrics = result['metrics']
    metrics['pr'] = dict(name='Intervalo PR global', unit='ms', value=None, status='unavailable', reason='Limites globais de P e QRS insuficientes.')
    if len(rr) >= 2 and np.all((rr >= .25) & (rr <= 3)):
        metrics['heart_rate'].update(value=round(60 / median_rr, 1), status='experimental', reason='',
                                     method=rhythm['method'], rr_median_seconds=median_rr)
    representatives = {}; stacks = {}
    points, sources, local = {}, {}, {}
    if accepted:
        stacks = {}
        for kind in ('raw', 'qrs', 'pt'):
            stacks[kind] = np.stack([c[kind][c['p'] + c['shift'] - pre:c['p'] + c['shift'] + post + 1] for c in accepted])
        medians = {lead: {kind: np.median(stacks[kind][:, :, ch], axis=0) for kind in stacks}
                   for ch, lead in enumerate(names)}
        smoothing = {}
        unsmoothed = {lead: medians[lead]['qrs'].copy() for lead in names}
        for lead in names:
            smoothing[lead] = {}
            for kind in ('qrs', 'pt'):
                medians[lead][kind], smoothing[lead][kind] = smooth_median(medians[lead][kind])
        if len(accepted) >= 3 and median_rr:
            points, sources, local = global_boundaries(medians, pre, median_rr)
            rhythm['p_association'] = p_association(stacks['pt'], medians, points)
        for ch, lead in enumerate(names):
            representatives[lead] = dict(unsmoothed_values_mv=unsmoothed[lead]*factor, postprocessing=smoothing[lead], values_mv=medians[lead]['qrs'] * factor, raw_values_mv=medians[lead]['raw'] * factor,
                pt_values_mv=medians[lead]['pt'] * factor, aligned_beats_mv=stacks['qrs'][:, :, ch] * factor,
                time_seconds=(np.arange(pre + post + 1) - pre) / FS, r_index=pre,
                markers=[dict(kind=key, index=value, time_seconds=(value - pre) / FS) for key, value in points.items()],
                group_size=len(accepted), discarded_beats=len(excluded),
                source_first_sample=result['first_sample'], source_last_sample_exclusive=result['last_sample_exclusive'],
                source_centers=audit['source_centers'], source_beat_indices=list(range(len(accepted))),
                original_peaks=audit['original_peaks'], translation_samples=audit['translation_samples'],
                median_operation='pointwise; shared integer translation; bounded post-smoothing; no amplitude normalization or temporal warp',
                visual_eligible=True, measurement_eligible=bool(points), clinical_confidence=False,
                template_measurement_pipeline='QRS 0.5–80 Hz; P/T 0.5–30 Hz; zero phase; bounded SG 7/4 after median',
                measurement_reasons=[] if points else ['Limites globais insuficientes; mediana preservada.'])
    for key, on, off in [('p_duration', 'pon', 'poff'), ('qrs_duration', 'qon', 'qoff'), ('qt', 'qon', 'toff'), ('pr', 'pon', 'qon')]:
        metric = metrics[key]
        metric.update(method=METHOD, boundary_source='global_medians', accepted_beats=len(accepted), candidate_beats=len(candidates))
        if on in points and off in points and points[off] > points[on]:
            metric.update(value=round((points[off] - points[on]) / FS * 1000, 1), status='estimated', reason='')
        else:
            metric['reason'] = 'Limites globais insuficientes nas medianas; curva preservada.'
    qt = metrics['qt']['value']; qtc = metrics['qtc_f']; qrs = metrics['qrs_duration']['value']
    rhythm['premature'] = analyze_premature(candidates, excluded, audit, qrs, pre, post, cancelled)
    qtc.update(method=METHOD, boundary_source='global_medians', formula='QTcF = QT(ms) / RR(s)^(1/3)')
    blockers = qtc_blockers(qt, qrs, rr)
    if not blockers:
        qtc.update(value=round(qt / np.cbrt(median_rr), 1), status='estimated', reason='')
    else:
        qtc['reason'] = ' '.join(blockers)
    result.update(status='experimental' if representatives else 'unavailable', global_fiducials=dict(r=pre, **points),
                  boundary_provenance=sources, local_candidates=local,
                  rr_variability=float(rr.std() / rr.mean()) if len(rr) else None)
    from .measurement_quality import assess,attach_metrics
    attach_metrics(result,assess(stacks,names,pre,median_rr,points,sources,factor,cancelled))
    result['descriptions'] = [dict(id='qrs_width', status='descriptive' if qrs is not None else 'unavailable',
        text=f'QRS global: {qrs:g} ms.' if qrs is not None else 'QRS global indisponível.',
        criterion='Início mais precoce e fim mais tardio sustentados pelas medianas das derivações disponíveis; estimativa exploratória, sem classificação diagnóstica.')]
    result['descriptions'] += [dict(id='morphology_exclusion', status='descriptive',
        text=f"{len(accepted)} batimentos na mediana; {len(excluded)} excluídos por morfologia; {len(incomplete)} sem janela completa.",
        criterion='Exclusão simultânea nas derivações; RR e frequência preservam a sequência original.')]
    result['descriptions'] += [
        dict(id='bundle_branch',status='unavailable',text='Bloqueio de ramo específico: indisponível.',
             reason='Requer critérios morfológicos e derivações precordiais ausentes; duração QRS isolada não os substitui.') ]
    for item in excluded + incomplete:
        result['descriptions'].append(dict(id='excluded_' + str(item['sample']), status='descriptive',
            text=f"Batimento em {(r.times[item['sample']] - r.meta['start']):.3f} s fora da mediana.", reason=item['reason']))
    for key, item in sources.items():
        label = {'pon':'início P','poff':'fim P','qon':'início QRS','qoff':'fim QRS','ton':'início T','toff':'fim T'}[key]
        result['descriptions'].append(dict(id='boundary_' + key, status='descriptive', text=f'{label}: {(item["index"] - pre) / FS * 1000:.1f} ms em relação ao QRS.',
            criterion='Sustentado por ' + ', '.join(item['supporting_leads']) + '; aplicado a todas as medianas.'))
    for key,quality in result['technical_quality']['boundaries'].items():
        if quality.get('reason'):result['descriptions'].append(dict(id='quality_'+key,status='descriptive',text=quality['reason'],criterion='Estabilidade técnica nas medianas de subconjuntos; não representa acurácia clínica.'))
    for lead in names:
        item = deepcopy({key: val for key, val in result.items() if key != 'additional_leads'})
        item.update(lead=lead, median=representatives.get(lead))
        if lead == 'I':
            result['median'] = item['median']
        else:
            result['additional_leads'].append(item)
    qtc_label = f'QTc: {qtc["value"]:g} ms (global; Fridericia)' if qtc['value'] is not None else 'QTc global: indisponível'
    if qtc.get('quality',{}).get('reason'):qtc_label+=' · revisar medida'
    return result, representatives, audit, qtc_label
