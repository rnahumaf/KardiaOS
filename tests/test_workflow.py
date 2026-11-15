import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from kardiaos.app import Window, synthetic_pairs
from kardiaos.signal import FilterConfig


@pytest.fixture
def window():
    application = QApplication.instance() or QApplication([])
    w = Window(demo=True)
    w.tick_timer.stop()
    yield w
    w.live = w.dirty = False
    w.close()


def feed(w, seconds=3):
    base = time.monotonic() - seconds
    for i in range(0, int(seconds * 300), 9):
        w.accept_samples(base + i / 300, synthetic_pairs(i, 9))


def test_waits_for_contact_then_starts_clock(window):
    window.start()
    for i in range(40):
        window.accept_samples(i * .03, np.full((9, 2), 25000))
    assert window.recording.meta['start'] is None
    assert window.accepted_wall is None
    assert window.paper.overlay
    feed(window)
    assert window.recording.meta['start'] is not None
    assert window.accepted_wall is not None
    assert not window.paper.overlay


def test_contact_loss_and_disconnection_preserve_samples(window):
    window.start()
    feed(window)
    n = window.recording.n
    for i in range(40):
        window.accept_samples(time.monotonic() + i * .03, np.full((9, 2), 25000))
    assert window.state_label.text() == 'Ajuste o contato'
    assert not window.recording.quality[window.recording.n - 1]
    window.stop_reason = 'Dispositivo desconectado'
    window.finish()
    assert window.recording.n > n
    assert window.save_button.isEnabled()
    assert window.recording.meta['reason'] == 'Dispositivo desconectado'


def test_manual_filter_visible_without_modifying_raw(window):
    window.start()
    feed(window)
    raw = window.recording.raw[:window.recording.n].copy()
    before = window.recording.filtered[:window.recording.n].copy()
    window.auto.setChecked(False)
    window.apply_filters(FilterConfig(.05, 80, 0))
    np.testing.assert_array_equal(window.recording.raw[:window.recording.n], raw)
    assert not np.allclose(window.recording.filtered[:window.recording.n], before)


def test_duration_stops_and_preserves(window):
    window.start()
    feed(window)
    window.demo = False  # Keep tick from appending additional synthetic data.
    window.accepted_wall = time.monotonic() - 31
    window.tick()
    assert not window.live
    assert window.recording.n > 0
    assert window.recording.meta['reason'] == 'Duração programada concluída'


def test_live_single_lead_is_accepted_and_changes_with_contacts(window):
    window.start()
    base = time.monotonic() - 6
    for i in range(0, 900, 9):
        samples = synthetic_pairs(i, 9)
        samples[:, 1] |= 1
        window.accept_samples(base + i / 300, samples)
    r = window.recording
    assert r.meta['start'] is not None
    assert r.mode_at() == 1
    assert np.isnan(r.lead_values()[:, 1:]).all()
    assert 'Somente D1' in window.state_label.toolTip()
    for i in range(900, 1500, 9):
        window.accept_samples(base + i / 300, synthetic_pairs(i, 9))
    assert r.mode_at() == 6
    assert 'Seis derivações' in window.state_label.toolTip()
    samples = synthetic_pairs(1503, 9)
    samples[:, 1] |= 1
    window.accept_samples(base + 1503 / 300, samples)
    assert r.mode_at() == 1
    assert np.isnan(r.lead_values(r.n - 9)[:, 1:]).all()
    assert np.isfinite(r.lead_values(r.n - 9)[:, 0]).all()
