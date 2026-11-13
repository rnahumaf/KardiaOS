"""Causal research filters. No beat replacement, interpolation, or amplitude fitting."""
from dataclasses import dataclass, asdict
import numpy as np
from scipy import signal

FS = 300
MV_PER_COUNT = 10.0 / 65536  # Provisional specification-derived scale, not calibration.
LEADS = ("D1", "D2", "D3", "aVR", "aVL", "aVF")


def six_leads(two):
    a = np.asarray(two, dtype=np.float64)
    i, ii = a[..., 0], a[..., 1]
    return np.stack((i, ii, ii - i, -(i + ii) / 2, i - ii / 2, ii - i / 2), axis=-1)


@dataclass(frozen=True)
class FilterConfig:
    baseline: float = 0.5
    lowpass: float = 40.0
    notch: int = 60

    def validate(self):
        if self.baseline not in (0, 0.05, 0.5, 1.0):
            raise ValueError("Filtro de linha de base inválido.")
        if self.lowpass not in (0, 25, 40, 80):
            raise ValueError("Filtro de suavização inválido.")
        if self.notch not in (0, 50, 60):
            raise ValueError("Filtro de rede inválido.")
        return self

    def to_dict(self):
        return asdict(self)


class Processor:
    def __init__(self, config=FilterConfig()):
        self.config = config.validate()
        sections = []
        if config.baseline:
            sections.append(signal.butter(1, config.baseline, btype="highpass", fs=FS, output="sos"))
        if config.notch:
            b, a = signal.iirnotch(config.notch, 30, fs=FS)
            sections.append(signal.tf2sos(b, a))
        if config.lowpass:
            sections.append(signal.butter(2, config.lowpass, fs=FS, output="sos"))
        self.sos = np.concatenate(sections) if sections else np.empty((0, 6))
        self.zi = None

    def reset(self):
        self.zi = None

    def process(self, values):
        x = np.asarray(values, dtype=np.float64)
        if not len(x) or not len(self.sos):
            return x.copy()
        if self.zi is None:
            self.zi = signal.sosfilt_zi(self.sos)[:, :, None] * x[0][None, None, :]
        y, self.zi = signal.sosfilt(self.sos, x, axis=0, zi=self.zi)
        return y

    def delay_ms(self, frequency=10):
        if not len(self.sos):
            return 0.0
        f = np.array([frequency - 0.01, frequency + 0.01])
        _, h = signal.sosfreqz(self.sos, worN=f, fs=FS)
        return max(0.0, -np.diff(np.unwrap(np.angle(h)))[0] / (2 * np.pi * np.diff(f)[0]) * 1000)


def automatic_config(raw):
    """Choose noise controls from spectral energy; never use rhythm regularity."""
    x = np.asarray(raw, dtype=float)
    if len(x) < FS * 2:
        return FilterConfig()
    f, psd = signal.welch(x, fs=FS, nperseg=min(len(x), FS * 2), axis=0)
    power = np.mean(psd, axis=1)
    total = max(float(np.sum(power[(f >= 5) & (f <= 100)])), 1e-12)
    mains = {hz: float(np.sum(power[abs(f - hz) < 1.5])) for hz in (50, 60)}
    peak = max(mains, key=mains.get)
    notch = peak if mains[peak] / total > 0.035 else 0
    high_noise = np.sum(power[(f > 45) & (f < 100)]) / total
    return FilterConfig(0.5, 25 if high_noise > 0.30 else 40, notch)


def contact_ok(raw):
    """Conservative artifact gate, not a physiological normality detector."""
    x = np.asarray(raw, dtype=float)
    if len(x) < FS // 2:
        return False
    if np.any(np.mean(np.abs(x) > 24000, axis=0) > 0.06):
        return False
    if np.any(np.std(x, axis=0) < 3):
        return False
    if np.any(np.percentile(np.abs(np.diff(x, axis=0)), 90, axis=0) > 6000):
        return False
    return True


def reprocess(raw, timestamps, config):
    result = np.empty(np.shape(raw), dtype=float)
    processor = Processor(config)
    boundaries = np.r_[0, np.flatnonzero(np.diff(timestamps) > 0.12) + 1, len(raw)]
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        processor.reset()
        result[left:right] = processor.process(raw[left:right])
    return result
