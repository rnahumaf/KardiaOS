"""Exercise acquisition limits, session review and rhythm with missing data."""

import numpy as np
import pytest
from PySide6.QtCore import QSettings

from kardiaos.app import Window, synthetic_pairs
from kardiaos.automatic_analysis import analysis_key, automatic_analysis, cached_analysis
from kardiaos.recording import load_recording, save_recording
from kardiaos.report import page_plan
from kardiaos.research import inspect_window
from kardiaos.rule_analysis import classify
from kardiaos.signal import FS
from test_measurements import signal_record
from test_rule_analysis import case, status


@pytest.mark.parametrize('mode, expected', [('di', 1), ('six', 6)])
def test_acquisition_selector_caps_leads_even_with_two_available_codes(tmp_path, monkeypatch, mode, expected):
    class LocalStream:
        def start(self):
            pass

    monkeypatch.setattr('kardiaos.app.Stream', LocalStream)
    window = Window(settings=QSettings(str(tmp_path/'prefs.ini'), QSettings.Format.IniFormat))
    window.tick_timer.stop()
    window.autorun.setChecked(False)
    assert window.capture_mode.currentData() == 'di'
    window.capture_mode.setCurrentIndex(window.capture_mode.findData(mode))
    window.start()
    assert not window.capture_mode.isEnabled()
    raw = synthetic_pairs(0, 900)
    assert not (raw & 3).any()
    for i in range(0, len(raw), 9):
        window.accept_samples(i/FS, raw[i:i+9])
    record = window.recording
    assert record.meta['acquisition_mode'] == mode
    assert record.mode_at() == expected
    np.testing.assert_array_equal(record.raw[:record.n], raw)
    if mode == 'di':
        assert np.isnan(record.lead_values()[:, 1:]).all()
    else:
        assert np.isfinite(record.lead_values()[-1]).all()
    window.finish()
    assert window.capture_mode.isEnabled()
    window.dirty = False


def test_review_as_di_is_session_only_including_analysis_pdf_and_models(tmp_path, monkeypatch):
    path = tmp_path/'original.kardia'
    save_recording(path, signal_record())
    original = path.read_bytes()
    monkeypatch.setattr('kardiaos.app.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    window = Window(demo=True, settings=QSettings(str(tmp_path/'prefs.ini'), QSettings.Format.IniFormat))
    window.tick_timer.stop()
    window.autorun.setChecked(False)
    window.open_recording()
    record = window.recording
    modes = record.lead_modes[:record.n].copy()
    six = automatic_analysis(record)
    window.background_result(record, six)
    key = analysis_key(record)
    assert len(six['representative']) == 6 and not window.review_di_button.isHidden()

    window.review_di_button.click()
    window._analysis_timer.stop()
    assert record.review_as_di and not window.dirty
    assert analysis_key(record) != key and cached_analysis(record) is None
    assert record.mode_at() == 1 and np.isnan(record.lead_values(raw=True)[:, 1:]).all()
    result = automatic_analysis(record)
    assert list(result['representative']) == ['I']
    assert result['classification']['summary'] == 'Ritmo regular compatível com sinusal em DI'
    assert page_plan(record, analysis=result)['layout'] == 'di'
    assert inspect_window(record, 'deeppsp_2l', require_calibration=False)['status'] != 'ready'
    np.testing.assert_array_equal(record.lead_modes[:record.n], modes)
    saved = tmp_path/'saved.kardia'
    save_recording(saved, record)
    assert load_recording(saved).mode_at() == 6

    window.review_di_button.click()
    window._analysis_timer.stop()
    assert record.mode_at() == 6 and analysis_key(record) == key
    window.review_di_button.click()
    window._analysis_timer.stop()
    window.open_recording()
    assert path.read_bytes() == original
    assert not window.review_di_button.isChecked() and window.recording.mode_at() == 6


@pytest.mark.parametrize('loss, eligible', [(153, True), (660, False)])
def test_rhythm_uses_concordant_segments_without_rr_crossing_the_gap(loss, eligible):
    record = signal_record()
    gap = 5000
    record.times[gap:record.n] += .11
    record.quality[gap:gap+loss] = False
    record.meta['end'] = record.last_time
    result = automatic_analysis(record)
    rhythm = result['measurements']['alignment']['rhythm']
    assert rhythm['coverage']['fraction'] > .9
    assert len(rhythm['p_association']['segments']) == 2
    assert all(not a < gap <= b for a, b in rhythm['rr_pairs'])
    classification = result['classification']
    assert classification['sinus_supported'] is eligible
    assert any('trechos válidos' in text for text in classification['sinus_limitations'])


def test_tachycardia_in_di_is_separate_from_rhythm():
    record = signal_record(rr=.585, t_center=.23)
    record.review_as_di = True
    result = automatic_analysis(record)
    assert result['classification']['summary'] == 'Ritmo regular compatível com sinusal em DI'
    assert status(result['classification'], 'tachy') == 'detected'


def test_only_an_unstable_pr_close_to_the_limit_is_borderline():
    record, measurement, representatives = case()
    pr = measurement['metrics']['pr']
    pr.update(value=116.7, quality=dict(status='review', reason='Marcos variáveis entre subconjuntos.'))
    rule = next(v for v in classify(record, measurement, representatives)['rules'] if v['id'] == 'pr_short')
    assert rule['status'] == 'not_detected' and '116,7 ms' in rule['possible_context']
    assert 'Marcos variáveis' in rule['possible_context'] and pr['value'] == 116.7
    pr['value'] = 113.3
    assert status(classify(record, measurement, representatives), 'pr_short') == 'detected'
