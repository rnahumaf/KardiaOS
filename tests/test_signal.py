import struct
import numpy as np
from kardiaos.ble import decode_m2
from kardiaos.signal import Processor, FilterConfig, six_leads, automatic_config, contact_ok, reprocess, FS


def test_exact_packet_decoding():
    pairs = ((-32768, 32767), (-1, 0), (123, -456)) * 3
    assert decode_m2(b''.join(struct.pack('<hh', *x) for x in pairs)) == pairs


def test_limb_lead_identities_no_integer_overflow():
    x = np.array([[32767, -32768], [100, 200]], dtype=np.int16)
    leads = six_leads(x)
    np.testing.assert_array_equal(leads[:, 2], leads[:, 1] - leads[:, 0])
    np.testing.assert_allclose(leads[:, 3:].sum(axis=1), 0)
    assert leads[0, 2] == -65535


def test_streaming_matches_batch_and_never_changes_raw():
    x = np.random.default_rng(7).normal(size=(3000, 2))
    original = x.copy()
    expected = Processor().process(x)
    processor = Processor()
    actual = np.vstack([processor.process(x[i:i + 9]) for i in range(0, len(x), 9)])
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    np.testing.assert_array_equal(original, x)


def test_reduces_mains_and_baseline_preserves_signal_band():
    t = np.arange(6000) / FS
    clean = np.sin(2 * np.pi * 10 * t)
    x = clean + np.sin(2 * np.pi * 60 * t) + 3 * np.sin(2 * np.pi * .1 * t)
    y = Processor().process(np.column_stack((x, x)))[:, 0]
    def magnitude(values, hz):
        return abs(np.dot(values[3000:], np.exp(-2j * np.pi * hz * t[3000:]))) / 1500
    assert magnitude(y, 60) < .02
    assert magnitude(y, .1) < magnitude(x, .1) * .25
    assert .85 < magnitude(y, 10) < 1.1
    assert Processor().delay_ms() < 30


def test_automatic_mains_choice():
    t = np.arange(1200) / FS
    for hz in (50, 60):
        x = np.sin(2 * np.pi * hz * t) * 1000 + np.sin(2 * np.pi * 8 * t) * 300
        assert automatic_config(np.column_stack((x, x))).notch == hz


def test_quality_rejects_rails_and_flat_contact_not_irregular_rhythm():
    assert not contact_ok(np.full((300, 2), 25000))
    assert not contact_ok(np.zeros((300, 2)))
    x = np.random.default_rng(4).normal(0, 400, (300, 2))
    assert contact_ok(x)


def test_gap_resets_filter_state():
    x = np.vstack((np.full((300, 2), 1000), np.full((300, 2), -1000)))
    times = np.r_[np.arange(300) / FS, 2 + np.arange(300) / FS]
    y = reprocess(x, times, FilterConfig())
    assert np.max(abs(y[300:])) < 1e-8
