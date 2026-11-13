"""Model-specific offline preprocessing. Sources and revisions: assets/research_catalog.json.

The recorded operational profile may filter upstream. This worker only applies
the pinned model contract; no missing-lead filling, beat replacement or rhythm correction.
The 300 -> 500 Hz polyphase adapter changes sampling density, not bandwidth.
"""
import numpy as np
from scipy.signal import resample_poly, iirnotch, butter, filtfilt, medfilt


def preprocess(values_mv, model_key):
    x = np.asarray(values_mv, dtype=np.float64)
    channels = {'ecgfounder_1l': 1, 'deeppsp_2l': 2, 'deeppsp_6l': 6}.get(model_key)
    if channels is None or x.shape != (channels, 3000) or not np.isfinite(x).all():
        raise ValueError('Entrada incompatível: são necessários 10 s contínuos a 300 Hz.')
    if np.any(np.std(x, axis=1) < 1e-8):
        raise ValueError('Sinal constante ou sem variação suficiente.')
    x = resample_poly(x, 5, 3, axis=1)
    if model_key == 'ecgfounder_1l':
        # ECGFounder util.filter_bandpass + dataset.LVEF_1lead_cls_Dataset.
        b, a = iirnotch(50, 30, 500)
        x = filtfilt(b, a, x, axis=1)
        b, a = butter(4, [0.67, 40], btype='bandpass', fs=500)
        x = filtfilt(b, a, x, axis=1)
        x = x - np.stack([medfilt(row, kernel_size=201) for row in x])
        x = (x - x.mean()) / (x.std() + 1e-8)
    else:
        # DeepPSP saved train_config is authoritative, not the newer master defaults.
        # Out-of-range signals are rejected instead of replacing >20 mV spikes.
        if np.any(np.abs(x) > 20):
            raise ValueError('Amplitude acima de 20 mV; conferir escala/artefato. Nenhuma amostra foi substituída.')
        b, a = butter(5, [0.5, 60], btype='bandpass', fs=500)
        x = filtfilt(b, a, x, axis=1)
        # normalize_data=True in both pinned train_config objects; global, not per lead.
        x = (x - x.mean()) / (x.std() + 1e-7)
    if not np.isfinite(x).all():
        raise ValueError('Pré-processamento produziu valores não finitos.')
    return np.ascontiguousarray(x, dtype=np.float32)
