import zipfile
import json
import numpy as np
import pytest
from kardiaos.recording import Recording, save_recording, load_recording


def fixture():
    r = Recording(synthetic=True)
    for i in range(10):
        r.append(i * .03, np.array([[i, -i]] * 9), good=i >= 3)
    r.meta.update(start=.09, end=r.last_time)
    return r


def test_lossless_roundtrip(tmp_path):
    r = fixture()
    path = tmp_path / 'synthetic.kardia'
    save_recording(path, r)
    loaded = load_recording(path)
    np.testing.assert_array_equal(loaded.raw[:loaded.n], r.raw[:r.n])
    np.testing.assert_array_equal(loaded.times[:loaded.n], r.times[:r.n])
    np.testing.assert_array_equal(loaded.quality[:loaded.n], r.quality[:r.n])
    assert loaded.meta['synthetic']


def test_gap_preserved_in_time(tmp_path):
    r = fixture()
    r.append(1, [[8, -8]] * 9, good=False)
    assert r.times[r.n - 9] - r.times[r.n - 10] > .7
    assert r.gaps == 1


def test_tampered_file_rejected(tmp_path):
    path = tmp_path / 'good.kardia'
    save_recording(path, fixture())
    with zipfile.ZipFile(path) as archive:
        data = {k: archive.read(k) for k in archive.namelist()}
    data['raw.npy'] += b'x'
    bad = tmp_path / 'bad.kardia'
    with zipfile.ZipFile(bad, 'w') as archive:
        for k, v in data.items():
            archive.writestr(k, v)
    with pytest.raises(ValueError, match='integridade'):
        load_recording(bad)
