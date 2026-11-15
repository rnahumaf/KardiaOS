"""Regression cases with known timing and independent synthetic lead projections."""

import numpy as np
import pytest
from PySide6.QtCore import Qt

from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from kardiaos.automatic_analysis import automatic_analysis
from kardiaos.evidence_view import evidence_data
from kardiaos.median_landmarks import combine_candidates
from kardiaos.recording import Recording
from kardiaos.signal import FS
from qt_synthetics import pulse


def premature_record():
    t = np.arange(31*FS)/FS
    x = np.zeros((len(t), 2))
    for index, r in enumerate(np.arange(.6, 31, 1.)):
        if index in (9, 20):
            p = r-.5
            x += pulse(t, p, .16, 1.)[:, None]*[-.95, 1.1]
            x += pulse(t, p+.24, .17, .22)[:, None]*[1., -.65]
        else:
            x += pulse(t, r, .08, 1.)[:, None]*[1., .65]
            x += pulse(t, r-.20, .10, .18)[:, None]*[1., .85]
            x += pulse(t, r+.27, .16, .28)[:, None]*[1., .7]
    r = Recording(synthetic=True)
    r.append(0, (np.rint(x*5000/4)*4).astype(np.int16), True)
    r.meta.update(start=1., end=r.last_time)
    r.quality[:FS] = False  # quality before the effective start is irrelevant
    return r


def test_premature_group_has_own_duration_and_preserves_original_rr():
    record = premature_record()
    raw = record.raw.copy()
    result = automatic_analysis(record)
    m = result['measurements']
    rhythm = m['alignment']['rhythm']
    events = rhythm['premature']['events']
    assert [event['sample']/FS for event in events] == pytest.approx([9.1, 20.1], abs=.01)
    assert all(event['ventricular_pattern'] and event['group_size'] == 2 for event in events)
    assert all(event['qrs_ms'] == pytest.approx(160, abs=12) for event in events)
    assert m['metrics']['qrs_duration']['value'] == pytest.approx(80, abs=12)
    assert m['metrics']['heart_rate']['value'] == 60
    assert m['metrics']['qtc_f']['value'] is None
    assert [rr for rr in rhythm['rr_seconds'] if rr != 1] == [.5, 1.5, .5, 1.5]
    assert result['classification']['summary'] == 'Ritmo de base sinusal, 2 batimentos prematuros e RR irregular'
    for key in ('brady', 'tachy'):
        rate = evidence_data(record, result, key)
        assert rate['row']['status'] == 'not_detected'
        assert rate['rr_median'] == 1 and not rate['rr_highlights'].any()
    assert evidence_data(record, result, 'irregular')['rr_highlights'].sum() == 4
    np.testing.assert_array_equal(record.raw, raw)


def test_isolated_early_p_requires_sustained_deflection():
    candidates = {
        'aVR': {'p': dict(pon=36, poff=74, quality=45, onset_supported=False)},
        'II': {'p': dict(pon=46, poff=76, quality=40, onset_supported=True)},
        'aVF': {'p': dict(pon=48, poff=74, quality=41, onset_supported=True)},
    }
    points, provenance = combine_candidates(candidates, 'p', 'pon', 'poff')
    assert points == {'pon': 46, 'poff': 76}
    assert provenance['pon']['rejected_onsets'][0]['index'] == 36
    assert provenance['pon']['supporting_leads'] == ['II']
    candidates['aVR']['p']['onset_supported'] = True
    assert combine_candidates(candidates, 'p', 'pon', 'poff')[0]['pon'] == 36


def test_grouped_criteria_navigate_to_both_complexes(qt_application):
    record = premature_record()
    result = automatic_analysis(record)
    dialog = AutomaticAnalysisDialog(record, autostart=False)
    dialog.on_result(result)
    dialog.resize(850, 650)
    dialog.show()
    dialog.criteria_toggle.click()
    qt_application.processEvents()
    negative = dialog.rule_tables['not_detected']
    assert negative.rowCount() and not negative.isVisible()
    dialog.rule_toggles['not_detected'][1].click()
    assert negative.isVisible()
    positives = dialog.rule_tables['detected']
    i = next(i for i in range(positives.rowCount())
             if positives.item(i, 0).data(Qt.ItemDataRole.UserRole) == 'premature')
    positives.cellActivated.emit(i, 0)
    qt_application.processEvents()
    panel = dialog.evidence_panel
    assert panel.data['key'] == 'premature' and panel.table.rowCount() == 2
    assert all(set(curves) == {'DIII', 'aVF'} for _, curves in panel.plot.event_curves)
    assert not panel.plot.grab().isNull()
    dialog.close()
