"""Known synthetic timing and distortion budgets; never patient fixtures."""
import numpy as np
import pytest
from kardiaos.median_landmarks import smooth_median, qrs_candidate, combine_candidates
from kardiaos.global_median import analyze
from qt_synthetics import pulse
from test_measurements import signal_record


@pytest.mark.parametrize('width', [.06, .08, .12, .16, .20])
@pytest.mark.parametrize('sign', [1, -1])
def test_qrs_boundaries_follow_known_pulse_feet(width, sign):
    t = (np.arange(286)-105)/300
    original = sign * pulse(t, 0, width, 1)
    smoothed, _ = smooth_median(original)
    points, reason = qrs_candidate(smoothed, 105)
    assert points, reason
    assert (points['qon']-105)/300 == pytest.approx(-width/2, abs=.007)
    assert (points['qoff']-105)/300 == pytest.approx(width/2, abs=.007)
    assert np.argmax(abs(smoothed)) == 105


def test_smoothing_reduces_ripple_with_bounded_amplitude_change_and_no_shift():
    t = (np.arange(286)-105)/300
    original = pulse(t, 0, .08, 1) + .015*np.cos(2*np.pi*65*t)
    smoothed, metadata = smooth_median(original)
    assert np.max(abs(smoothed-original)) <= .015*np.ptp(original) + 1e-12
    assert abs(np.ptp(smoothed)-np.ptp(original)) <= .03*np.ptp(original)
    # A fourth-degree, seven-sample fit deliberately attenuates 65 Hz only
    # modestly. Check its reduction away from the polynomial edge treatment.
    assert np.std(np.diff(smoothed[4:65], n=2)) < .95*np.std(np.diff(original[4:65], n=2))
    assert np.argmax(smoothed) == np.argmax(original) == 105
    assert metadata['amplitude_rescaling'] is False
    np.testing.assert_allclose(smooth_median(-3*original)[0], -3*smoothed, atol=1e-12)
    np.testing.assert_allclose(smooth_median(original+4)[0], smoothed+4, atol=1e-12)


def test_flat_projection_stays_flat_and_has_no_qrs():
    smoothed, _ = smooth_median(np.zeros(286))
    np.testing.assert_array_equal(smoothed, 0)
    assert not qrs_candidate(smoothed, 105)[0]


def test_weak_remote_candidate_cannot_extend_global_qrs_but_strong_one_can():
    candidates = {
        'I': {'qrs': dict(qon=93, qoff=121, quality=100)},
        'II': {'qrs': dict(qon=92, qoff=122, quality=90)},
        'aVF': {'qrs': dict(qon=90, qoff=140, quality=20)},
    }
    points, provenance = combine_candidates(candidates, 'qrs', 'qon', 'qoff')
    assert points == dict(qon=92, qoff=122)
    assert 'aVF' in provenance['qoff']['rejected_candidates']
    candidates['aVF']['qrs']['quality'] = 70
    points, provenance = combine_candidates(candidates, 'qrs', 'qon', 'qoff')
    assert points == dict(qon=90, qoff=140)
    assert provenance['qoff']['supporting_leads'] == ['aVF']


def test_detector_receives_exact_displayed_smoothed_medians(monkeypatch):
    from kardiaos import global_median
    original = global_median.delineate_medians
    captured = {}
    def inspect(medians, anchor, rr):
        captured.update({lead: {k: v.copy() for k, v in values.items()} for lead, values in medians.items()})
        return original(medians, anchor, rr)
    monkeypatch.setattr(global_median, 'delineate_medians', inspect)
    r = signal_record()
    _, representatives, _, _ = analyze(r)
    factor, _ = global_median.scale_and_signs(r)
    for lead, rep in representatives.items():
        np.testing.assert_array_equal(rep['values_mv'], captured[lead]['qrs']*factor)
        np.testing.assert_array_equal(rep['pt_values_mv'], captured[lead]['pt']*factor)


@pytest.mark.parametrize('noise', [0, .025])
def test_complete_pipeline_preserves_known_intervals_with_background_noise(noise):
    m, _, _, _ = analyze(signal_record(noise=noise))
    for key, truth, tolerance in [('p_duration', 100, 25), ('qrs_duration', 80, 10),
                                  ('qt', 400, 25), ('pr', 210, 15)]:
        assert m['metrics'][key]['value'] == pytest.approx(truth, abs=tolerance)


def test_wide_qrs_retains_width_and_does_not_receive_routine_qtc():
    m, _, _, _ = analyze(signal_record(qrs_width=.16))
    assert m['metrics']['qrs_duration']['value'] == pytest.approx(160, abs=10)
    assert m['metrics']['qtc_f']['value'] is None
