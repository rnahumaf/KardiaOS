import json
import zipfile
import numpy as np
import pytest
from kardiaos.contact import ContactTracker
from kardiaos.recording import Recording, save_recording, load_recording
from kardiaos.app import synthetic_pairs


@pytest.mark.parametrize('flag', [1, 2, 3])
def test_missing_second_channel_never_derives_other_leads(flag):
    raw = synthetic_pairs(0, 900)
    raw[:, 1] |= flag
    r = Recording(synthetic=True)
    r.append(0, raw, True)
    assert np.all(r.lead_modes[:r.n] == 1)
    assert np.isfinite(r.lead_values()[:, 0]).all()
    assert np.isnan(r.lead_values()[:, 1:]).all()
    np.testing.assert_array_equal(r.raw[:r.n], raw)


def test_loss_immediate_recovery_requires_confirmation():
    tracker = ContactTracker()
    assert tracker.update(np.zeros((150, 2), dtype=np.int16))[-1] == 6
    assert tracker.update([[0, 1]])[0] == 1
    assert np.all(tracker.update(np.zeros((149, 2), dtype=np.int16)) == 1)
    assert tracker.update([[0, 0]])[0] == 6
    assert tracker.update([[1, 0]])[0] == 0


def test_legacy_and_new_recordings_keep_contact_and_raw(tmp_path):
    r = Recording(synthetic=True)
    values = synthetic_pairs(0, 900)
    values[600:, 1] |= 1
    r.append(0, values, True)
    r.meta.update(start=1, end=r.last_time)
    path = tmp_path / 'synthetic.kardia'
    save_recording(path, r)
    loaded = load_recording(path)
    np.testing.assert_array_equal(loaded.lead_modes[:r.n], r.lead_modes[:r.n])
    with zipfile.ZipFile(path) as archive:
        data = {name: archive.read(name) for name in archive.namelist() if name != 'lead_modes.npy'}
    meta = json.loads(data['metadata.json'])
    meta['version'] = 1
    del meta['hashes']['lead_modes.npy']
    data['metadata.json'] = json.dumps(meta).encode()
    legacy = tmp_path / 'legacy.kardia'
    with zipfile.ZipFile(legacy, 'w') as archive:
        for name, content in data.items():
            archive.writestr(name, content)
    loaded = load_recording(legacy)
    np.testing.assert_array_equal(loaded.lead_modes[:r.n], r.lead_modes[:r.n])
    np.testing.assert_array_equal(loaded.raw[:r.n], values)
    assert np.isfinite(loaded.lead_values(300, 600)).all()
    assert np.isnan(loaded.lead_values(600)[:, 1:]).all()
