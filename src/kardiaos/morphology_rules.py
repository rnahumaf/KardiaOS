"""Descriptive morphology on the smoothed median, with explicit weak evidence.

These noise, width and prominence cutoffs are engineering heuristics, not
diagnostic thresholds or calibrated probabilities. Indices are wave-relative.
"""
import numpy as np
from scipy.signal import find_peaks


def describe_wave(values, noise, kind):
    y = np.asarray(values, dtype=float)
    result = dict(biphasic=dict(status='not_detected', components=[]),
                  notched=dict(status='not_detected', components=[]))
    if len(y) < 7 or not np.isfinite(y).all():
        for item in result.values(): item['status'] = 'unavailable'
        return result
    amplitude = float(np.max(abs(y)))
    weak = max(2*noise, .01 if kind == 'p' else .015, .05*amplitude)
    strong = max(3*noise, .03 if kind == 'p' else .05)
    lobes = []
    for sign in (1, -1):
        peaks, props = find_peaks(sign*y, height=weak, prominence=weak, width=2, distance=6)
        if len(peaks):
            j = int(np.argmax(props['peak_heights'])); index = int(peaks[j])
            lobes.append(dict(index=index, amplitude_mv=float(y[index]),
                              prominence_mv=float(props['prominences'][j])))
    if len(lobes) == 2:
        result['biphasic'] = dict(status='detected' if all(abs(v['amplitude_mv']) >= strong and v['prominence_mv'] >= strong for v in lobes) else 'possible',
                                  components=sorted(lobes, key=lambda v:v['index']))
    result['biphasic']['thresholds']=dict(possible_mv=weak,defined_mv=strong,minimum_width_samples=2,minimum_distance_samples=6)
    if kind != 't': return result
    sign = 1 if y[np.argmax(abs(y))] >= 0 else -1
    z = sign*y
    weak_notch = max(2*noise, .005, .06*float(np.ptp(y)))
    strong_notch = max(3*noise, .015, .15*float(np.ptp(y)))
    peaks, props = find_peaks(z, height=weak, prominence=weak_notch, distance=6, width=2)
    pairs = []
    for i in range(len(peaks)-1):
        a,b = int(peaks[i]),int(peaks[i+1])
        valley = a+int(np.argmin(z[a:b+1])); depth = float(min(z[a],z[b])-z[valley])
        ratio = float(min(z[a],z[b])/max(z[a],z[b]))
        if depth < weak_notch or ratio < .15: continue
        clear = depth >= strong_notch and ratio >= .3
        pairs.append(dict(status='detected' if clear else 'possible', depth=depth,
            components=[dict(index=k, amplitude_mv=float(y[k])) for k in (a,valley,b)]))
    if pairs:
        best = max(pairs,key=lambda v:(v['status']=='detected',v['depth']))
        result['notched'] = dict(status=best['status'],components=best['components'],depth_mv=best['depth'])
    result['notched']['thresholds']=dict(possible_depth_mv=weak_notch,defined_depth_mv=strong_notch,possible_peak_ratio=.15,defined_peak_ratio=.3)
    return result
