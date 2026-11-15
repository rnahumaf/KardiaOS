import io
import json
from types import SimpleNamespace
import numpy as np
import pytest
from kardiaos.app import synthetic_pairs
from kardiaos.recording import Recording, save_recording, load_recording
from kardiaos.signal import FilterConfig
from kardiaos import research
from kardiaos.research_preprocess import preprocess


def capture(single=False, synthetic=True):
    r = Recording(synthetic=synthetic)
    values = synthetic_pairs(0, 3300)
    if single:
        values[:, 1] |= 1
    r.append(0, values, good=True)
    r.meta.update(start=1.0, end=r.last_time)
    return r


def successful_worker(*args, **kwargs):
    with np.load(io.BytesIO(kwargs['input']), allow_pickle=False) as payload:
        spec = research.catalog()['models'][str(payload['model_key'])]
    return SimpleNamespace(returncode=0, stdout=json.dumps(dict(status='ok', scores=[0.25]*len(spec['labels']),
        checkpoint_sha256=spec['sha256'], runtime='test-double', elapsed_seconds=0, preprocessing='test')).encode())


def test_real_capture_is_exploratory_without_validating_reference(monkeypatch):
    r = capture(synthetic=False)
    monkeypatch.setattr(research, 'runtime_config', lambda: dict(python='unused', models_dir='unused'))
    monkeypatch.setattr(research.subprocess, 'run', successful_worker)
    for key in research.catalog()['models']:
        result = research.analyze(r, key)
        assert result['status'] == 'experimental' and result['scores']
        assert result['mode'] == 'exploratory' and not result['clinical_validation']
        assert not result['calibration_verified']
        assert result['evidence']['decoder'] == {'I': None, 'II': None}
        assert not any(result['evidence']['amplitude'].values())
    r.meta['amplitude_verified'] = True
    assert not research.calibration_valid(r)
    r.meta['research_calibration'] = dict(reference='Synthetic test reference', polarity_verified=True, mv_per_count=r.meta['mv_per_count'])
    assert not research.calibration_valid(r)
    r.meta['mv_per_count'] *= 2
    assert not research.calibration_valid(r)


@pytest.mark.parametrize('key', ['ecgfounder_1l', 'deeppsp_2l', 'deeppsp_6l'])
@pytest.mark.parametrize('profile', ['referenced', 'research-empirical-v1'])
def test_manual_neural_input_preserves_raw_scale_and_sign_for_every_profile(monkeypatch, key, profile):
    from copy import deepcopy
    from kardiaos.processing import set_profile
    from kardiaos.signal import six_leads
    from test_orientation import evidence
    r = capture(synthetic=False)
    set_profile(r, profile)
    evidence(r, 'decoder', 'I', -1)
    evidence(r, 'decoder', 'II', -1)
    r.meta['mv_per_count'] *= 2
    raw = r.raw[:r.n].copy()
    meta = deepcopy(r.meta)
    payloads = []
    monkeypatch.setattr(research, 'runtime_config', lambda: dict(python='unused', models_dir='unused'))
    def run(*args, **kwargs):
        with np.load(io.BytesIO(kwargs['input']), allow_pickle=False) as payload:
            payloads.append(payload['values_mv'].copy())
        return successful_worker(*args, **kwargs)
    monkeypatch.setattr(research.subprocess, 'run', run)
    a = research.analyze(r, key)
    assert a['status'] == 'experimental'
    assert r.meta == meta
    r.configure(FilterConfig(1.0, 25, 50))
    assert research.analyze(r, key)['status'] == 'experimental'
    count = 1 if key == 'ecgfounder_1l' else 2
    expected = raw[300:3300, :count].astype(float)*r.meta['mv_per_count']
    if key == 'deeppsp_6l': expected = six_leads(expected)
    np.testing.assert_array_equal(payloads[0], expected.T)
    np.testing.assert_array_equal(payloads[1], expected.T)
    np.testing.assert_array_equal(r.raw[:r.n], raw)
    assert a['input_contract']['raw_multipliers'] == [1]*count
    assert a['input_contract']['amplitude_multiplier'] == 1
    assert not a['input_contract']['display_filters_applied']


@pytest.mark.parametrize('factor', [0, -1, float('nan'), float('inf'), 'invalid'])
def test_invalid_scale_does_not_start_runtime(monkeypatch, factor):
    r = capture(synthetic=False); r.meta['mv_per_count'] = factor
    monkeypatch.setattr(research, 'runtime_config', lambda: pytest.fail('Invalid input reached runtime'))
    result = research.analyze(r, 'ecgfounder_1l')
    assert result['status'] == 'inconclusive' and result['reasons'] == ['Fator de amplitude inválido.']


def test_missing_second_lead_and_transport_gap_cannot_be_filled():
    r = capture(single=True)
    assert research.inspect_window(r, 'ecgfounder_1l')['status'] == 'ready'
    assert research.inspect_window(r, 'deeppsp_2l')['status'] == 'inconclusive'
    assert research.inspect_window(r, 'deeppsp_6l')['status'] == 'inconclusive'
    r.times[1500:r.n] += 0.2
    r.meta['end'] = r.last_time
    result = research.inspect_window(r, 'ecgfounder_1l')
    assert any('lacuna' in text for text in result['reasons'])


@pytest.mark.parametrize('bad', ['quality', 'short', 'frequency', 'flat', 'offset'])
def test_invalid_window_abstains(bad):
    r = capture()
    offset = 0
    if bad == 'quality': r.quality[800] = False
    if bad == 'short': r.n -= 1
    if bad == 'frequency': r.meta['sample_rate'] = 500
    if bad == 'flat': r.raw[300:r.n, 0] = 0
    if bad == 'offset': offset = float('nan')
    result = research.inspect_window(r, 'ecgfounder_1l', offset)
    assert result['status'] == 'inconclusive' and not result['scores']


def test_native_format_preserves_calibration_reference_and_raw(tmp_path):
    r = capture(synthetic=False)
    r.meta.update(amplitude_verified=True, research_calibration=dict(reference='Test reference only', polarity_verified=True, mv_per_count=r.meta['mv_per_count']))
    path = tmp_path / 'synthetic.kardia'
    save_recording(path, r)
    loaded = load_recording(path)
    assert not research.calibration_valid(loaded)
    np.testing.assert_array_equal(loaded.raw[:loaded.n], r.raw[:r.n])


def test_inference_uses_raw_and_ignores_visual_filters(monkeypatch):
    r = capture()
    raw = r.raw[:r.n].copy()
    payloads = []
    monkeypatch.setattr(research, 'runtime_config', lambda: dict(python='unused', models_dir='unused'))
    def run(*args, **kwargs):
        with np.load(io.BytesIO(kwargs['input']), allow_pickle=False) as payload:
            payloads.append(payload['values_mv'].copy())
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(status='ok', scores=[0.25]*150,
            checkpoint_sha256='test', runtime='test-double', elapsed_seconds=0, preprocessing='test')).encode())
    monkeypatch.setattr(research.subprocess, 'run', run)
    assert research.analyze(r, 'ecgfounder_1l')['status'] == 'synthetic'
    r.configure(FilterConfig(1.0, 25, 50))
    research.analyze(r, 'ecgfounder_1l')
    np.testing.assert_array_equal(payloads[0], payloads[1])
    np.testing.assert_array_equal(r.raw[:r.n], raw)


def test_invalid_runtime_scores_never_become_results(monkeypatch):
    monkeypatch.setattr(research, 'runtime_config', lambda: dict(python='unused', models_dir='unused'))
    monkeypatch.setattr(research.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'{"status":"ok","scores":[1]}'))
    result = research.analyze(capture(), 'ecgfounder_1l')
    assert result['status'] == 'inconclusive' and result['scores'] == []


@pytest.mark.parametrize('key,n', [('ecgfounder_1l',1),('deeppsp_2l',2),('deeppsp_6l',6)])
def test_resampling_preserves_time_and_preprocessing_is_finite(key,n):
    t = np.arange(3000)/300
    x = np.tile(np.sin(2*np.pi*10*t), (n,1))
    y = preprocess(x,key)
    assert y.shape == (n,5000) and y.dtype == np.float32 and np.isfinite(y).all()
    hz = np.fft.rfftfreq(5000,1/500)[np.argmax(np.abs(np.fft.rfft(y[0])))]
    assert hz == 10


def test_catalog_preserves_real_heads_and_labels():
    models = research.catalog()['models']
    assert len(models['ecgfounder_1l']['labels']) == 150
    for key in ['deeppsp_2l','deeppsp_6l']:
        labels = models[key]['labels']
        assert len(labels) == 21
        q = next(item for item in labels if item['abbreviation'] == 'QAb')
        assert q['name'] == 'qwave abnormal' and q['code'] == '164917005'
        assert not any(label['abbreviation'] in ['Brady','LAD','RAD','PR','LQRSV'] for label in labels)
        assert all(not lead.startswith('V') for lead in models[key]['leads'])
