"""Behavioral tests with synthetic signals; no personal recordings in the repo."""
import numpy as np
import pytest
from kardiaos.global_median import analyze, VERSION
from kardiaos.automatic_analysis import automatic_analysis
from kardiaos.recording import Recording
from kardiaos.report import pdf_bytes, page_plan
from test_measurements import signal_record
from test_automatic_analysis import fake_infer
from qt_synthetics import make


def test_all_leads_share_beats_shifts_and_global_markers_even_when_avf_flat():
    r = signal_record()
    # aVF = II - I/2: a truly flat projection must not run its own QRS detector.
    r.raw[:r.n, 0] = (r.raw[:r.n, 0] // 8) * 8
    r.raw[:r.n, 1] = r.raw[:r.n, 0] // 2
    before = r.raw.copy()
    m, reps, audit, _ = analyze(r)
    assert len(reps) == 6 and audit['accepted_beats'] > 20
    for rep in reps.values():
        assert rep['source_centers'] == reps['I']['source_centers']
        assert rep['translation_samples'] == reps['I']['translation_samples']
        assert rep['markers'] == reps['I']['markers']
        np.testing.assert_allclose(rep['unsmoothed_values_mv'], np.median(rep['aligned_beats_mv'], axis=0))
        original = np.asarray(rep['unsmoothed_values_mv'])
        assert max(abs(rep['values_mv'] - original)) <= .015 * np.ptp(original) + 1e-12
    np.testing.assert_array_equal(reps['aVF']['values_mv'], 0)
    assert 'aVF' not in m['boundary_provenance']['qon']['supporting_leads']
    assert m['metrics']['qrs_duration']['value'] == pytest.approx(80, abs=25)
    assert m['metrics']['p_duration']['value'] == pytest.approx(100, abs=25)
    np.testing.assert_array_equal(before, r.raw)


@pytest.mark.parametrize('case', ['ectopic_QRS', 'translation_jitter', 'irregular'])
def test_shared_morphology_decision_preserves_original_rhythm(case):
    x, refs = make(case)
    r = Recording(synthetic=True)
    raw = np.round(x / 4).astype(np.int16) * 4
    r.append(0, np.column_stack([raw, raw // 2 & -4]), True)
    r.meta.update(start=0., end=r.last_time)
    m, reps, audit, _ = analyze(r)
    assert len(reps) == 6
    assert len(audit['rhythm']['detected_peaks']) >= len(refs)
    assert max(abs(v) for v in audit['translation_samples']) <= 12
    if case == 'ectopic_QRS':
        assert any(abs(v['sample'] / 300 - 3.6) < .1 for v in audit['excluded'])
        assert any(abs(v / 300 - 3.6) < .1 for v in audit['rhythm']['detected_peaks'])
        assert all(abs(v / 300 - 3.6) > .1 for v in audit['original_peaks'])
        assert all(v['scope'] == 'all_leads' for v in audit['excluded'])
    else:
        assert not audit['excluded']
    if case == 'irregular':
        assert m['metrics']['qtc_f']['value'] is None


def test_t_only_outlier_excluded_from_all_leads_but_not_rr():
    r = signal_record()
    time = r.times[:r.n]
    mask = (time > 8.75) & (time < 8.99)
    r.raw[:r.n][mask] *= -1
    _, reps, audit, _ = analyze(r)
    assert any('Morfologia de T' in v['reason'] for v in audit['excluded'])
    assert len(reps) == 6
    assert any(abs(v / 300 - 8.6) < .05 for v in audit['rhythm']['detected_peaks'])


def test_no_individual_delineation_or_neural_fallback(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Individual beat or neural timing must not run')
    r = signal_record(t=False)
    monkeypatch.setattr('kardiaos.delineation.delineate', forbidden)
    # Direct median engine does not use the legacy detector/delineator at all.
    m, reps, _, _ = analyze(r)
    assert len(reps) == 6 and m['metrics']['qt']['value'] is None
    assert m['metrics']['p_duration']['value'] is not None
    assert m['metrics']['qrs_duration']['value'] is not None
    assert not m['fiducials']
    result = automatic_analysis(r, infer=fake_infer, qt_infer=forbidden)
    assert result['measurements']['metrics']['qt']['value'] is None


def test_report_window_does_not_change_median_measurements_or_rhythm():
    def forbidden(*args, **kwargs):
        raise AssertionError('Retired QT segmenter must not influence measurements')
    r = signal_record()
    a = automatic_analysis(r, infer=fake_infer, qt_infer=forbidden, offset=0, duration=10)
    b = automatic_analysis(r, infer=fake_infer, qt_infer=forbidden, offset=12, duration=10)
    assert a['report_window']['first_sample'] != b['report_window']['first_sample']
    assert a['measurements'] == b['measurements']
    assert a['representative'] == b['representative']
    assert a['qt']['neural_segmenter_used'] is False
    assert a['measurements']['method_version'] == VERSION
    for result in (a, b):
        assert not result['scenarios']
        assert result['classification']['version'] == 'limb-rules-3'
        assert all(v['last_sample_exclusive'] - v['first_sample'] == 3000 for v in result['scenarios'])
        assert len(page_plan(r, analysis=result)['rows']) == 6
        assert pdf_bytes(r, analysis=result).startswith(b'%PDF')


def test_gap_and_contact_loss_never_join_beats_or_rr():
    r = signal_record()
    r.quality[3000:3600] = False
    r.times[6000:r.n] += .5
    r.meta['end'] = r.last_time
    _, reps, audit, _ = analyze(r)
    assert len(reps) == 6
    assert all(.95 < v < 1.05 for v in audit['rhythm']['rr_seconds'])
    for center in audit['source_centers']:
        assert not (3000 - 180 <= center < 3600 + 105)
        assert not (6000 - 180 <= center < 6000 + 105)


def test_global_boundary_provenance_and_polarity_invariance():
    a, _, _, _ = analyze(signal_record())
    b, _, _, _ = analyze(signal_record(invert=True, gain=.5))
    for key in ('p_duration', 'qrs_duration', 'qt', 'pr', 'qtc_f'):
        assert a['metrics'][key]['value'] is not None
        assert b['metrics'][key]['value'] == pytest.approx(a['metrics'][key]['value'], abs=7)
    for key, evidence in a['boundary_provenance'].items():
        expected = min(evidence['candidates'].values()) if key.endswith('on') else max(evidence['candidates'].values())
        assert evidence['index'] == expected == a['global_fiducials'][key]
    for lead in a['additional_leads']:
        assert lead['global_fiducials'] == a['global_fiducials']


def test_single_lead_never_fabricates_other_derivations():
    r = signal_record()
    r.raw[:r.n, 1] |= 1
    r.lead_modes[:r.n] = 1
    m, reps, _, _ = analyze(r)
    assert list(reps) == ['I'] and m['additional_leads'] == []


def test_rhythm_keeps_i_only_portion_of_mixed_recording():
    r = signal_record()
    r.raw[4500:r.n, 1] |= 1
    r.lead_modes[4500:r.n] = 1
    _, reps, audit, _ = analyze(r)
    assert len(reps) == 6 and max(audit['source_centers']) < 4500
    assert max(audit['rhythm']['detected_peaks']) > 8500


def test_missing_wave_does_not_hide_any_median():
    m, reps, _, _ = analyze(signal_record(p=False, t=False))
    assert len(reps) == 6
    assert m['metrics']['p_duration']['value'] is None
    assert m['metrics']['qt']['value'] is None
    assert m['metrics']['qrs_duration']['value'] is not None
    assert all(rep['visual_eligible'] for rep in reps.values())
