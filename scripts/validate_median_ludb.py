"""Compare whole-record median P and QRS landmarks with manual LUDB limb-lead annotations."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import numpy as np
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from kardiaos.global_median import analyze
from kardiaos.processing import scale_and_signs
from kardiaos.recording import Recording

LEADS = ('i', 'ii', 'iii', 'avr', 'avl', 'avf')
WAVES = {'P': ('pon', 'poff'), 'QRS': ('qon', 'qoff')}


def read_case(folder, ident):
    import wfdb  # Optional dependency in requirements-validation.txt.
    path = str(folder / 'data' / str(ident))
    record = wfdb.rdrecord(path, channels=[0, 1])
    if record.fs != 500 or tuple(record.sig_name) != LEADS[:2] or record.sig_len != 5000:
        raise ValueError('Expected the 10-second, 500 Hz LUDB 1.0.1 limb-lead recording.')
    references = []
    for lead in LEADS:
        ann = wfdb.rdann(path, lead)
        waves = [(symbol, *np.asarray(ann.sample[j-1:j+2])/500)
                 for j, symbol in enumerate(ann.symbol) if symbol in ('p', 'N')
                 and j > 0 and ann.symbol[j-1] == '(' and ann.symbol[j+1:j+2] == [')']]
        references.append(waves)
    return record.p_signal, references


def reference_bounds(center, leads):
    observed = {wave: [] for wave in WAVES}
    for waves in leads:
        near = [q for q in waves if q[0] == 'N' and abs(q[2]-center) <= .1]
        if not near:
            continue
        q = min(near, key=lambda w: abs(w[2]-center))
        observed['QRS'].append(q)
        previous_end = max((w[3] for w in waves if w[0] == 'N' and w[2] < q[2]), default=-np.inf)
        p = [w for w in waves if w[0] == 'p' and max(q[2]-.4, previous_end) < w[2] < q[1]]
        if len(p) == 1:
            observed['P'].append(p[0])
    # The extreme limits of all requested annotated leads represent a global interval.
    return {wave: (np.array([min(w[1] for w in group), max(w[3] for w in group)])-center)*1000
            for wave, group in observed.items() if len(group) == len(leads)}


def baseline_delineator(ref):
    source = subprocess.check_output(['git', 'show', f'{ref}:src/kardiaos/median_landmarks.py'], cwd=ROOT)
    module = ModuleType('kardiaos._baseline_landmarks')
    module.__package__ = 'kardiaos'
    exec(compile(source, '<baseline median_landmarks.py>', 'exec'), module.__dict__)
    return module.delineate_medians


def evaluate_case(raw, annotations, mode, baseline):
    record = Recording(synthetic=True, acquisition_mode=mode)
    record.append(0, raw, True)
    record.meta.update(start=0., end=record.last_time)
    record.lead_modes[:record.n] = 1 if mode == 'di' else 6
    m, reps, audit, _ = analyze(record)
    predictions = {'current': m['global_fiducials']}
    if baseline:
        predictions['baseline'] = {}
        rr = audit['rhythm']['rr_seconds']
        if audit['accepted_beats'] >= 3 and rr:
            factor, _ = scale_and_signs(record)
            medians = {lead: {'qrs': rep['values_mv']/factor, 'pt': rep['pt_values_mv']/factor}
                       for lead, rep in reps.items()}
            predictions['baseline'] = baseline(medians, reps['I']['r_index'], np.median(rr))[0]
    leads = annotations[:1] if mode == 'di' else annotations
    matched = [reference_bounds(index/300, leads) for index in audit['source_centers']]
    anchor = m['global_fiducials']['r']
    for wave, (on, off) in WAVES.items():
        bounds = [b[wave] for b in matched if wave in b]
        any_label = any(w[0] == ('p' if wave == 'P' else 'N') for lead in leads for w in lead)
        for name, p in predictions.items():
            available = on in p and off in p
            error = None
            if available and len(bounds) >= 3:
                error = (np.array([p[on], p[off]])-anchor)*1000/300 - np.median(bounds, axis=0)
            yield (mode, wave, name), (len(bounds) >= 3, any_label, available, error)


def summarize(rows):
    errors = np.array([e for _, _, _, e in rows if e is not None]).reshape(-1, 2)
    return dict(records=len(rows), comparable=sum(ok for ok, _, _, _ in rows), measured=len(errors),
                both_within_20_ms=int(np.sum(np.max(abs(errors), axis=1) <= 20+1e-9)),
                onset_offset_mae_ms=np.round(abs(errors).mean(axis=0), 2).tolist() if len(errors) else None,
                no_annotation=sum(not label for _, label, _, _ in rows),
                measured_without_annotation=sum(not label and measured for _, label, measured, _ in rows))


def evaluate(ids, read, baseline=None):
    results = {}
    for ident in ids:
        mv, annotations = read(ident)
        raw = np.rint(resample_poly(mv, 3, 5, axis=0)*1024)*4
        if np.max(abs(raw)) >= 32760:
            raise ValueError('Quantization would saturate the recording.')
        for mode in ('di', 'six'):
            for key, row in evaluate_case(raw.astype(np.int16), annotations, mode, baseline):
                results.setdefault(key, []).append(row)
    return {'/'.join(key): summarize(rows) for key, rows in results.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True, help='LUDB 1.0.1 directory containing data/')
    parser.add_argument('--split', choices=('development', 'held_out'), default='held_out')
    parser.add_argument('--baseline', help='Trusted Git revision of the previous median delineator')
    args = parser.parse_args()
    people = np.random.default_rng(1729).permutation(np.arange(1, 201))
    ids = people[:40] if args.split == 'development' else people[40:]
    baseline = baseline_delineator(args.baseline) if args.baseline else None
    print(json.dumps(evaluate(ids, lambda i: read_case(args.data, i), baseline), indent=2))
