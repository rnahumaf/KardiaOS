"""Manual neural entry, queued models and rendered results use synthetic fixtures."""
import json
from threading import Event

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

from kardiaos import research
from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from kardiaos.research_dialog import ResearchDialog
from test_analysis_dialog import wait
from test_measurements import signal_record
from test_research import capture, successful_worker


def mock_runtime(monkeypatch):
    monkeypatch.setattr(research, 'runtime_config', lambda: dict(python='unused', models_dir='unused'))
    monkeypatch.setattr(research.subprocess, 'run', successful_worker)


def test_open_runs_all_models_at_selected_offset_and_repeats(monkeypatch, qt_application):
    mock_runtime(monkeypatch)
    calls = []
    def analyze(record, key, offset):
        calls.append((key, offset))
        return research.analyze(record, key, offset)
    monkeypatch.setattr('kardiaos.research_dialog.analyze', analyze)
    r = signal_record(); r.meta['synthetic'] = False
    d = ResearchDialog(r)
    d.offset.setValue(8)
    d.show()
    wait(qt_application, lambda: len(calls) == 3 and not d.busy())
    assert calls == [(key, 8) for key in research.catalog()['models']]
    assert [p.table.rowCount() for p in d.panes] == [150, 21, 21]
    assert all(p.export_button.isEnabled() and p.run_button.isEnabled() for p in d.panes)
    assert d.offset.isEnabled() and d.run_all.isEnabled()
    assert d.recording is not r and d.recording.raw.flags.writeable is False
    for i, pane in enumerate(d.panes):
        d.tabs.setCurrentIndex(i); qt_application.processEvents()
        assert pane.table.isVisible() and pane.result['status'] == 'experimental'
        assert 'não calibrados' in pane.state.text()
    d.offset.setValue(7)
    assert all(p.result is None and p.table.rowCount() == 0 and not p.export_button.isEnabled() for p in d.panes)
    assert len(calls) == 3
    QTest.mouseClick(d.run_all, Qt.MouseButton.LeftButton)
    wait(qt_application, lambda: len(calls) == 6 and not d.busy())
    assert calls[3:] == [(key, 7) for key in research.catalog()['models']]
    d.reject(); assert not d.isVisible()


def test_busy_state_blocks_duplicates_and_close_until_finished(monkeypatch, qt_application):
    mock_runtime(monkeypatch)
    entered, release = Event(), Event()
    calls = []
    def analyze(record, key, offset):
        calls.append(key); entered.set()
        if not release.wait(10): raise RuntimeError('Synthetic worker was not released')
        return research.analyze(record, key, offset)
    monkeypatch.setattr('kardiaos.research_dialog.analyze', analyze)
    d = ResearchDialog(capture()); d.show()
    try:
        wait(qt_application, entered.is_set)
        assert d.busy() and not d.offset.isEnabled() and not d.run_all.isEnabled()
        assert all(not p.run_button.isEnabled() for p in d.panes)
        assert 'Avaliando 1 de 3' in d.progress.text()
        assert 'Aguardando' in d.panes[1].state.text()
        d.start_all(); d.reject(); d.close()
        assert d.isVisible() and len(calls) == 1
    finally:
        release.set()
        wait(qt_application, lambda: not d.busy())
    assert len(calls) == 3 and d.run_all.isEnabled()
    d.close()


def test_missing_leads_are_not_queued_and_reason_is_visible(monkeypatch, qt_application):
    mock_runtime(monkeypatch)
    calls = []
    def analyze(record, key, offset):
        calls.append(key); return research.analyze(record, key, offset)
    monkeypatch.setattr('kardiaos.research_dialog.analyze', analyze)
    d = ResearchDialog(capture(single=True, synthetic=False)); d.show()
    wait(qt_application, lambda: bool(calls) and not d.busy())
    assert calls == ['ecgfounder_1l']
    assert d.panes[0].table.rowCount() == 150
    for pane in d.panes[1:]:
        assert pane.table.rowCount() == 0
        assert 'Não executado' in pane.state.text() and 'Derivações necessárias' in pane.state.text()
    assert '1 de 3 modelos com resultado' in d.progress.text()
    d.close()


def test_worker_failure_does_not_stop_other_models(monkeypatch, qt_application):
    mock_runtime(monkeypatch)
    def analyze(record, key, offset):
        if key == 'ecgfounder_1l': raise RuntimeError('Synthetic failure')
        return research.analyze(record, key, offset)
    monkeypatch.setattr('kardiaos.research_dialog.analyze', analyze)
    d = ResearchDialog(capture()); d.show()
    wait(qt_application, lambda: d.panes[-1].result is not None and not d.busy())
    assert 'Falha na análise local' in d.panes[0].state.text()
    assert [p.table.rowCount() for p in d.panes] == [0, 21, 21]
    assert d.run_all.isEnabled() and d.offset.isEnabled()
    d.close()


def test_no_compatible_window_finishes_without_inference(monkeypatch, qt_application):
    calls = []
    monkeypatch.setattr('kardiaos.research_dialog.analyze', lambda *args: calls.append(args))
    r = capture(); r.n -= 1
    d = ResearchDialog(r); d.show()
    wait(qt_application, lambda: all(p.result is not None for p in d.panes))
    assert not calls and not d.busy() and d.run_all.isEnabled()
    assert all('Não executado' in p.state.text() and '10 s completos' in p.state.text() for p in d.panes)
    assert '0 de 3 modelos com resultado' in d.progress.text()
    d.close()


def test_runtime_unavailable_has_specific_reason_for_each_model(monkeypatch, qt_application):
    def missing(): raise ValueError('Ambiente de pesquisa não configurado.')
    monkeypatch.setattr(research, 'runtime_config', missing)
    d = ResearchDialog(capture(synthetic=False)); d.show()
    wait(qt_application, lambda: d.panes[-1].result is not None and not d.busy())
    assert all('Ambiente de pesquisa não configurado' in p.state.text() for p in d.panes)
    assert all(p.table.rowCount() == 0 for p in d.panes)
    assert d.run_all.isEnabled()
    d.close()


def test_single_model_reevaluation_and_export_preserve_other_results(monkeypatch, qt_application, tmp_path):
    mock_runtime(monkeypatch)
    calls = []
    def analyze(record, key, offset):
        calls.append(key); return research.analyze(record, key, offset)
    monkeypatch.setattr('kardiaos.research_dialog.analyze', analyze)
    d = ResearchDialog(capture(synthetic=False)); d.show()
    wait(qt_application, lambda: d.panes[-1].result is not None and not d.busy())
    original = d.panes[0].result
    pane = d.panes[2]
    d.tabs.setCurrentIndex(2); qt_application.processEvents()
    QTest.mouseClick(pane.run_button, Qt.MouseButton.LeftButton)
    wait(qt_application, lambda: len(calls) == 4 and not d.busy())
    assert calls[-1] == 'deeppsp_6l' and d.panes[0].result is original
    destination = tmp_path/'synthetic-neural.json'
    monkeypatch.setattr('kardiaos.research_dialog.QFileDialog.getSaveFileName', lambda *args: (str(destination), 'JSON'))
    QTest.mouseClick(pane.export_button, Qt.MouseButton.LeftButton)
    saved = json.loads(destination.read_text(encoding='utf-8'))
    assert saved == pane.result and len(saved['scores']) == 21
    assert saved['input_contract']['raw_multipliers'] == [1, 1]
    assert saved['input_contract']['amplitude_multiplier'] == 1
    assert saved['evidence']['decoder'] == {'I': None, 'II': None}
    d.close()


def test_neural_button_opens_real_dialog_and_autostarts(monkeypatch, qt_application):
    mock_runtime(monkeypatch)
    d = AutomaticAnalysisDialog(signal_record(), autostart=False)
    d.show(); d.start()
    wait(qt_application, lambda: d.result is not None and d.neural_button.isEnabled() and not d.busy())
    observed = []
    def inspect_dialog():
        for child in d.findChildren(ResearchDialog):
            if child.panes[-1].result is not None and not child.busy():
                observed.append(([p.table.rowCount() for p in child.panes], child.offset.value()))
                child.reject()
    timer = QTimer(); timer.timeout.connect(inspect_dialog); timer.start(10)
    # Bound the nested modal loop even on regression so the test can report it.
    timeout = QTimer(); timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: [child.reject() for child in d.findChildren(ResearchDialog)])
    timeout.start(10000)
    try:
        QTest.mouseClick(d.neural_button, Qt.MouseButton.LeftButton)
    finally:
        timer.stop(); timeout.stop()
    assert observed == [([150, 21, 21], round(d.result['report_window']['offset_seconds'], 2))]
    d.close()


def test_close_before_autostart_does_not_run(monkeypatch, qt_application):
    monkeypatch.setattr('kardiaos.research_dialog.analyze', lambda *args: (_ for _ in ()).throw(AssertionError('Unexpected inference')))
    d = ResearchDialog(capture()); d.show(); d.close()
    qt_application.processEvents()
    assert not d.busy() and all(p.result is None for p in d.panes)
