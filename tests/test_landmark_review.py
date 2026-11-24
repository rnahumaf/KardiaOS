"""Manual median landmarks in classification, local recordings, UI and print."""
import io

import numpy as np
import pytest
from pypdf import PdfReader
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from kardiaos.automatic_analysis import automatic_analysis, cache_analysis
from kardiaos.landmark_editor import LandmarkEditor
from kardiaos.landmark_review import save_review, set_review_active, validate_points
from kardiaos.preview import PrintPreview
from kardiaos.recording import load_recording, save_recording
from kardiaos.report import page_plan, pdf_bytes
from test_analysis_dialog import wait
from test_main_flows_0110 import attach, window
from test_measurements import signal_record


def apply(record, result, points):
    state = result['measurements']['landmark_review']
    save_review(record, state, points, dict.fromkeys(points, 'I'))
    return automatic_analysis(record)


def test_revised_qrs_classifies_recomputes_and_survives_reopening(tmp_path):
    r = signal_record()
    auto = automatic_analysis(r)
    points = dict(auto['measurements']['landmark_review']['automatic_points'])
    points.update(qon=84, qoff=126)
    reviewed = apply(r, auto, points)
    m = reviewed['measurements']
    assert m['landmark_review']['origin'] == 'manual'
    assert m['metrics']['qrs_duration']['value'] == 140 and m['metrics']['qtc_f']['value'] is None
    page = PdfReader(io.BytesIO(pdf_bytes(r, analysis=reviewed))).pages[0].extract_text()
    assert f"QT: {m['metrics']['qt']['value']:g} ms" in page and 'QTcF: indisponível' in page
    assert m['metrics']['pr']['value'] == pytest.approx((84-points['pon'])/.3, abs=.05)
    assert m['metrics']['heart_rate']['value'] == auto['measurements']['metrics']['heart_rate']['value']
    assert 'qrs_wide' in {v['id'] for v in reviewed['classification']['findings']}
    assert not reviewed['classification']['possibilities']
    assert not cache_analysis(r, auto)
    path = tmp_path/'reviewed.kardia'
    save_recording(path, r); reopened = load_recording(path)
    repeated = automatic_analysis(reopened)
    assert repeated['measurements']['global_fiducials'] == m['global_fiducials']
    assert repeated['measurements']['landmark_review']['origin'] == 'manual'
    assert all(rep['markers'] == reviewed['representative']['I']['markers'] for rep in repeated['representative'].values())
    np.testing.assert_array_equal(reopened.raw[:reopened.n], r.raw[:r.n])
    set_review_active(r, m['landmark_review'], False)
    assert automatic_analysis(r)['measurements']['global_fiducials'] == auto['measurements']['global_fiducials']
    with pytest.raises(ValueError): page_plan(r, analysis=reviewed)


def test_manual_missing_wave_stays_missing_in_rules_and_pdf():
    r = signal_record()
    auto = automatic_analysis(r); pts = dict(auto['measurements']['landmark_review']['automatic_points'])
    pts.pop('pon'); pts.pop('poff')
    reviewed = apply(r, auto, pts)
    m = reviewed['measurements']
    assert m['metrics']['p_duration']['value'] is None and m['metrics']['pr']['value'] is None
    assert m['metrics']['qrs_duration']['status'] == 'reviewed'
    assert not reviewed['classification']['sinus_supported']
    text = PdfReader(io.BytesIO(pdf_bytes(r, analysis=reviewed))).pages[0].extract_text()
    assert 'P: indisponível' in text and 'Marcos revisados manualmente' in text


def test_omitting_only_qrs_end_preserves_reviewed_pr_and_qt():
    r = signal_record(); auto = automatic_analysis(r)
    points = dict(auto['measurements']['landmark_review']['automatic_points'])
    points.update(pon=points['qon']-48, poff=points['qon']-24)
    del points['qoff']
    reviewed = apply(r, auto, points)
    metrics = reviewed['measurements']['metrics']
    assert metrics['pr']['value'] == 160 and metrics['p_duration']['value'] == 80
    assert metrics['qt']['value'] == auto['measurements']['metrics']['qt']['value']
    assert metrics['qrs_duration']['value'] is None and metrics['qtc_f']['value'] is None
    assert reviewed['classification']['status'] == 'partial'
    page = PdfReader(io.BytesIO(pdf_bytes(r, analysis=reviewed))).pages[0].extract_text()
    for text in ['PR: 160 ms', 'QRS: indisponível', f"QT: {metrics['qt']['value']:g} ms",
                 'Duração do QRS indeterminada.']:
        assert text in page


@pytest.mark.parametrize('points', [{'pon': -1}, {'qoff': True}, {'r': 105}, {'qon': 107},
                                    {'pon': 40, 'poff': 40}, {'qoff': 140, 'ton': 125}])
def test_invalid_coordinates_are_rejected(points):
    with pytest.raises(ValueError): validate_points(points, 105, 286)


def test_review_is_scoped_to_the_median_and_malformed_data_cannot_override_it(monkeypatch):
    r = signal_record(); a = automatic_analysis(r); state = a['measurements']['landmark_review']
    apply(r, a, state['automatic_points'])
    monkeypatch.setattr('kardiaos.global_median.VERSION', 'same-curve-new-detector')
    assert automatic_analysis(r)['measurements']['landmark_review']['origin'] == 'manual'
    r.review_as_di = True
    assert automatic_analysis(r)['measurements']['landmark_review']['origin'] == 'automatic'
    r.review_as_di = False
    saved = r.meta['landmark_reviews']['six']
    previous = saved['point_leads']['qon']
    saved['point_leads']['qon'] = ['I']
    invalid = automatic_analysis(r)['measurements']['landmark_review']
    assert invalid['origin'] == 'automatic' and invalid['notice']
    saved['point_leads']['qon'] = previous
    r.meta['landmark_reviews']['six']['points']['qon'] = -1
    invalid = automatic_analysis(r)['measurements']['landmark_review']
    assert invalid['origin'] == 'automatic' and invalid['notice']
    r.meta['landmark_reviews']['six']['basis'] = 'different median'
    assert 'outra mediana' in automatic_analysis(r)['measurements']['landmark_review']['notice']


def test_editor_controls_reanalysis_and_print_source(qt_application, tmp_path, monkeypatch):
    r = signal_record(); auto = automatic_analysis(r); cache_analysis(r, auto)
    main = window(tmp_path); main.autorun.setChecked(False); attach(main, r)
    dialog = AutomaticAnalysisDialog(r, main, autostart=False); dialog.start(); dialog.show()
    def edits():
        editor = QApplication.activeModalWidget()
        assert isinstance(editor, LandmarkEditor)
        QTimer.singleShot(3000, editor, editor.reject)
        editor.table.selectRow(2); editor.lead.setCurrentIndex(1)
        editor.dispersion.click()
        assert editor.dispersion.isChecked() and not editor.plot.grab().isNull()
        editor.clear.click(); assert 'qon' not in editor.points
        box = editor.plot.graph(); lo, hi = editor.plot.domain()
        x = round(box.left()+(83-lo)*box.width()/(hi-lo))
        QTest.mouseClick(editor.plot, Qt.MouseButton.LeftButton, pos=QPoint(x, round(box.center().y())))
        QTest.keyClick(editor.plot, Qt.Key.Key_Right)
        assert editor.points['qon'] == 84 and editor.point_leads['qon'] == 'II'
        editor.table.selectRow(3); editor.place(126); editor.apply_button.click()
    QTimer.singleShot(0, edits); dialog.edit_landmarks()
    wait(qt_application, lambda: bool(dialog.result) and not dialog.busy())
    assert dialog.result['measurements']['metrics']['qrs_duration']['value'] == 140
    assert main.dirty and dialog.save_review_button.isVisible()
    assert 'Marcos revisados manualmente' in main.analysis_summary.text()
    saved = r.meta['landmark_reviews']['six']
    assert saved['point_leads']['qon'] == 'II'
    assert saved['point_leads']['pon'] == auto['measurements']['boundary_provenance']['pon']['supporting_leads'][0]
    def cancel_edit():
        editor = QApplication.activeModalWidget()
        editor.table.selectRow(2); editor.place(editor.state['anchor']+1)
        assert not editor.apply_button.isEnabled()
        editor.cancel_button.click()
    QTimer.singleShot(0, cancel_edit); dialog.edit_landmarks()
    assert r.meta['landmark_reviews']['six'] == saved and saved['points']['qon'] == 84
    path = tmp_path/'synthetic-review.kardia'
    monkeypatch.setattr('kardiaos.app.QFileDialog.getSaveFileName', lambda *_: (str(path), ''))
    dialog.save_review_button.click()
    assert path.exists() and not main.dirty
    preview = PrintPreview(r, analysis=dialog.result, autostart=False)
    assert preview.ready() and preview.point_origin.currentData() == 'manual'
    preview.choose_origin(preview.point_origin.findData('automatic'))
    assert preview.ready() and preview.analysis['measurements']['landmark_review']['origin'] == 'automatic'
    assert 'Marcos automáticos, sem revisão manual (menor confiança)' in PdfReader(io.BytesIO(preview.data)).pages[0].extract_text()
    preview.choose_origin(preview.point_origin.findData('manual'))
    assert preview.ready() and preview.analysis['measurements']['metrics']['qrs_duration']['value'] == 140
    assert r.meta['landmark_reviews']['six']['active'] is True
    preview.close(); dialog.close()
    monkeypatch.setattr('kardiaos.app.QFileDialog.getOpenFileName', lambda *_: (str(path), ''))
    main.open_button.click()
    assert main.recording is not r and main.recording.meta['landmark_reviews']['six'] == saved
    direct = PdfReader(io.BytesIO(main.report())).pages[0].extract_text()
    assert 'Marcos revisados manualmente' in direct and 'QRS: 140 ms' in direct
    main.close()
