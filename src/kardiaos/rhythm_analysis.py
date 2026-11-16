"""Separate the prevailing atrial rhythm from events in the original RR sequence."""

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import detrend, savgol_filter

from .median_landmarks import mad, smooth_median
from .signal import FS


def similarity(a, b):
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.sum(a*b) / denominator) if denominator > 1e-12 else -1.


def p_association(stack, medians, points, segment_starts):
    """Compare P shape and timing on the shared QRS clock, without new fiducials."""
    if 'I' not in medians or len(stack) < 5 or not all(k in points for k in ('pon', 'poff', 'qon')):
        return None
    left = max(0, points['pon']-3)
    right = min(points['poff']+4, points['qon']-3)
    if right-left < 12:
        return None
    leads = ['I', 'II'] if 'II' in medians else ['I']
    waves = np.column_stack([medians[lead]['pt'] for lead in leads])
    template = detrend(savgol_filter(waves, 13, 3, axis=0)[left:right], axis=0)
    norm = np.linalg.norm(template)
    if norm <= 1e-12:
        return None
    filtered = savgol_filter(stack[:, :, :len(leads)], 13, 3, axis=1)
    shifts = np.arange(max(-9, -left), min(9, points['qon']-3-right)+1)
    scores = []
    for shift in shifts:
        centered = detrend(filtered[:, left+shift:right+shift], axis=1)
        size = np.linalg.norm(centered, axis=(1, 2))
        score = np.sum(centered*template, axis=(1, 2)) / np.maximum(size*norm, 1e-12)
        scores.append(np.where(size >= .25*norm, score, -1.))
    scores = np.asarray(scores)
    best = np.argmax(scores, axis=0)
    matched = scores[best, np.arange(len(stack))] >= .75

    def summarize(eligible):
        observed = int(eligible.sum())
        passed = matched & eligible
        delays = shifts[best[passed]]
        spread = float(np.percentile(abs(delays-np.median(delays)), 90)*1000/FS) if len(delays) else None
        return dict(evaluated=observed, matched=len(delays), fraction=len(delays)/observed,
                    dispersion_ms=spread, supported=len(delays) >= .9*observed and spread is not None and spread <= 20)

    result = summarize(np.ones(len(stack), dtype=bool))
    segment_starts = np.asarray(segment_starts)
    groups = []
    for boundary in np.unique(segment_starts):
        eligible = segment_starts == boundary
        if eligible.sum() >= 5:
            groups.append(dict(summarize(eligible), first_sample=int(boundary)))
    return dict(result, leads=leads, segments=groups,
                supported=result['supported'] and all(v['supported'] for v in groups))


def rhythm_coverage(recording, qualified_segments):
    """Measure missing time, including transport gaps not represented in quality.npy."""
    start = float(recording.meta['start'])
    end = min(float(recording.meta.get('end') or recording.last_time), recording.last_time) + 1/FS
    duration = max(end-start, 1/FS)
    gaps = []
    previous = start
    for first, last in qualified_segments:
        gaps.append(float(recording.times[first]) - previous)
        previous = float(recording.times[last-1]) + 1/FS
    gaps.append(end-previous)
    observed = sum(last-first for first, last in qualified_segments)/FS
    return dict(seconds=observed, duration_seconds=duration, fraction=min(1., observed/duration),
                longest_gap_seconds=max(0., *gaps), segments=qualified_segments)


def _vector(curves):
    i, ii = curves[..., 0], curves[..., 1]
    return np.stack((i, (2*ii-i)/np.sqrt(3)), axis=-1)


def premature_qrs_extent(median, beats, anchor):
    """Delineate the QRS median, requiring reproducible weak flanks.

    Each slope estimate comes from the median of the aligned group. Individual
    slopes only verify whether the excursion reappears in its contributing beats.
    """
    if len(beats) < 2 or median.shape[1] < 2:
        return dict(reason='A largura requer pelo menos dois complexos semelhantes com duas derivações simultâneas.')
    central, repeated = _vector(median), _vector(beats)
    limits = []
    for width in (7, 9, 11):
        slope = np.gradient(savgol_filter(central, width, 3, axis=0), axis=0)
        repeated_slopes = np.gradient(savgol_filter(repeated, width, 3, axis=1), axis=1)
        magnitude = np.linalg.norm(slope, axis=1)
        projection = np.sum(repeated_slopes*slope, axis=2) / np.maximum(magnitude, 1e-12)
        corroborated = np.maximum(0., np.percentile(projection, 25, axis=0))
        envelope = uniform_filter1d(np.minimum(magnitude, np.sqrt(magnitude*corroborated)), 5)
        quiet = envelope[anchor-43:anchor-25]
        floor = float(np.median(quiet)) + 3*mad(quiet)
        peak = anchor-18 + int(np.argmax(envelope[anchor-18:anchor+19]))
        if envelope[peak] <= max(5*floor, 1e-12):
            continue
        for fraction in (.09, .105):
            active = envelope > max(floor, fraction*envelope[peak])
            left = right = peak
            while left > anchor-40 and np.any(active[left-5:left]):
                left -= 1
            while right < anchor+40 and np.any(active[right+1:right+6]):
                right += 1
            if anchor-40 < left < anchor < right < anchor+40:
                limits.append((left, right))
    if len(limits) < 4 or np.max(np.ptp(limits, axis=0)) > 6:
        return dict(reason='Início ou fim do QRS prematuro instável na mediana do grupo.')
    on, off = (int(v) for v in np.rint(np.median(limits, axis=0)))
    duration = (off-on)*1000/FS
    if not 40 <= duration <= 250:
        return dict(reason='Duração do QRS prematuro fora da faixa técnica.')
    return dict(on=on-anchor, off=off-anchor, qrs_ms=round(duration, 1),
                ranges_samples=[[int(v-anchor) for v in bounds]
                                for bounds in zip(np.min(limits, axis=0), np.max(limits, axis=0))])


def _shape(candidate, shift=0):
    center = candidate['p'] + shift
    return candidate['align'][center-45:center+46]


def _group_events(events):
    groups = []
    for event, candidate in events:
        best_group, best_shift, best_similarity = None, 0, .85
        for group in groups:
            reference = group[0][2]
            if reference.shape[1] != candidate['align'].shape[1]:
                continue
            score, _, shift = max((similarity(_shape(candidate, lag), reference), -abs(lag), lag)
                                  for lag in range(-12, 13))
            if score >= best_similarity:
                best_group, best_shift, best_similarity = group, shift, score
        if best_group is None:
            best_group = []
            groups.append(best_group)
        event['center'] = event['sample'] + best_shift
        best_group.append((event, candidate, _shape(candidate, best_shift)))
    return groups


def analyze_premature(candidates, exclusions, alignment, dominant_qrs, anchor, post, cancelled):
    """Use local RR for prematurity, retaining every valid RR for global measures."""
    from .automatic_analysis import Cancelled

    pairs = alignment['rhythm']['rr_pairs']
    before = {b: (a, b) for a, b in pairs}
    after = {a: (a, b) for a, b in pairs}
    distinct = {e['sample'] for e in exclusions if e.get('wave') == 'qrs'}
    evaluated = alignment['accepted_beats'] >= 5 and len(pairs) >= 4
    if not evaluated or not distinct:
        return dict(events=[], unresolved=sorted(distinct), evaluated=evaluated)
    normal_pairs = [(a, b) for a, b in pairs
                    if a not in distinct and b not in distinct and .25 <= (b-a)/FS <= 3]
    pending = set(distinct)
    matches = []
    for candidate in candidates:
        if cancelled():
            raise Cancelled()
        sample = candidate['absolute']
        if sample not in distinct or sample not in before:
            continue
        start = candidate['start']
        stop = start + len(candidate['qrs'])
        local = sorted(((a, b) for a, b in normal_pairs if start <= a < b < stop
                        and abs((a+b)//2-sample) <= 10*FS),
                       key=lambda pair: abs(sum(pair)-2*sample))[:8]
        if len(local) < 4:
            continue
        reference = float(np.median([b-a for a, b in local]))
        left = before[sample][0]
        right = after.get(sample, (None, None))[1]
        coupling = sample-left
        if coupling >= .8*reference:
            continue
        next_rr = right-sample if right is not None else None
        pause = next_rr is not None and next_rr > 1.1*reference and abs(coupling+next_rr-2*reference) <= .3*reference
        matches.append((dict(sample=sample, preceding_sample=left, following_sample=right,
                             coupling_ms=round(coupling*1000/FS, 1),
                             following_rr_ms=round(next_rr*1000/FS, 1) if next_rr is not None else None,
                             reference_rr_ms=round(reference*1000/FS, 1), pause_supported=pause), candidate))
        pending.remove(sample)
    events = []
    for number, group in enumerate(_group_events(matches), 1):
        slices = []
        for event, candidate, _ in group:
            center = event['center'] - candidate['start']
            slices.append(candidate['qrs'][center-anchor:center+post+1])
        beats = np.stack(slices)
        median = np.column_stack([smooth_median(y)[0] for y in np.median(beats, axis=0).T])
        bounds = premature_qrs_extent(median, beats, anchor)
        width = bounds.get('qrs_ms')
        wide = width is not None and width >= 120 and dominant_qrs is not None and width >= dominant_qrs+20
        for event, _, _ in group:
            event.update(bounds, morphology_group=number, group_size=len(group),
                         ventricular_pattern=bool(wide and event['pause_supported']))
            events.append(event)
    return dict(events=sorted(events, key=lambda event: event['sample']),
                unresolved=sorted(pending), evaluated=evaluated)
