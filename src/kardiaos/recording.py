"""Versioned, lossless local recordings. No pickle, no identifiers, no cloud."""
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import os
import zipfile
import numpy as np
from .signal import FS, MV_PER_COUNT, FilterConfig, Processor, reprocess, six_leads
from .orientation import evidence_state,DECODER_ID
from .contact import ContactTracker, infer_modes, channel_available
from .processing import scale_and_signs, profile_info, set_profile


class Recording:
    def __init__(self, synthetic=False):
        capacity = FS * 660
        self.raw = np.empty((capacity, 2), dtype=np.int16)
        self.filtered = np.empty((capacity, 2), dtype=np.float64)
        self.times = np.empty(capacity, dtype=np.float64)
        self.quality = np.zeros(capacity, dtype=bool)
        self.lead_modes = np.zeros(capacity, dtype=np.uint8)
        self.contact = ContactTracker()
        self.n = 0
        self.config = FilterConfig()
        self.processor = Processor(self.config)
        self.meta = dict(format="KardiaOS", version=2, sample_rate=FS,
                         created=datetime.now().astimezone().isoformat(), synthetic=synthetic, decoder_id=DECODER_ID,
                         start=None, end=None, reason="", mv_per_count=MV_PER_COUNT,
                         amplitude_verified=False, filter_history=[], duration_requested=30,
                         sample_clock="300 Hz nominal; gaps inferred from packet arrival >120 ms",
                         contact_detection="M2 low-two-bits, experimental, labeled 1L/6L evidence")
        self.last_arrival = None
        self.gaps = 0

    def append(self, arrived, samples, good=False):
        samples = np.asarray(samples, dtype=np.int16).reshape(-1, 2)
        if not len(samples):
            return
        if self.n + len(samples) > len(self.raw):
            raise ValueError("Limite de gravação alcançado.")
        start = self.times[self.n - 1] + 1 / FS if self.n else 0
        if self.last_arrival is not None and arrived - self.last_arrival > 0.12:
            start += max(0, arrived - self.last_arrival - len(samples) / FS)
            self.gaps += 1
            self.processor.reset()
            self.contact.reset()
        end = self.n + len(samples)
        self.raw[self.n:end] = samples
        self.times[self.n:end] = start + np.arange(len(samples)) / FS
        self.filtered[self.n:end] = self.processor.process(samples)
        self.quality[self.n:end] = good
        self.lead_modes[self.n:end] = self.contact.update(samples)
        self.last_arrival = arrived
        self.n = end

    def configure(self, config):
        self.config = config.validate()
        self.filtered[:self.n] = reprocess(self.raw[:self.n], self.times[:self.n], config)
        self.processor = Processor(config)
        if self.n:
            breaks = np.flatnonzero(np.diff(self.times[:self.n]) > 0.12)
            left = int(breaks[-1] + 1) if len(breaks) else 0
            self.processor.process(self.raw[left:self.n])
        self.meta["filter_history"].append(dict(at=float(self.times[self.n - 1]) if self.n else 0, **config.to_dict()))

    @property
    def last_time(self):
        return float(self.times[self.n - 1]) if self.n else 0.0

    def mode_at(self, timestamp=None):
        if not self.n:
            return 0
        index = self.n - 1 if timestamp is None else max(0, min(self.n - 1, int(np.searchsorted(self.times[:self.n], timestamp, side="right")) - 1))
        return int(self.lead_modes[index])

    def lead_values(self, first=0, last=None, raw=False):
        """Never derive voltages from a channel flagged as unavailable."""
        last = self.n if last is None else min(last, self.n)
        source = self.raw[first:last] if raw else self.filtered[first:last]
        factor, signs = scale_and_signs(self)
        source=source.astype(float)*np.array(signs)
        modes = self.lead_modes[first:last]
        available = channel_available(self.raw[first:last])
        result = np.full((last - first, 6), np.nan)
        one = (modes > 0) & available[:, 0] & self.quality[first:last]
        six = (modes == 6) & available.all(axis=1) & self.quality[first:last]
        result[one, 0] = source[one, 0]
        result[six] = six_leads(source[six])
        return result * factor


def save_recording(path, recording):
    if not recording.n:
        raise ValueError("Não há amostras para salvar.")
    blobs = {}
    for name, value in (("raw", recording.raw[:recording.n]), ("times", recording.times[:recording.n]), ("quality", recording.quality[:recording.n]), ("lead_modes", recording.lead_modes[:recording.n])):
        output = io.BytesIO()
        np.save(output, value, allow_pickle=False)
        blobs[name + ".npy"] = output.getvalue()
    meta = dict(recording.meta, version=2, filters=recording.config.to_dict(), hashes={k: hashlib.sha256(v).hexdigest() for k, v in blobs.items()})
    meta['operational_profile'] = profile_info(recording)
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("metadata.json", json.dumps(meta, ensure_ascii=False))
            for name, blob in blobs.items():
                archive.writestr(name, blob)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_recording(path):
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 20_000_000:
            raise ValueError("Arquivo maior que o limite suportado.")
        meta = json.loads(archive.read("metadata.json"))
        if meta.get("format") != "KardiaOS" or meta.get("version") not in (1, 2) or meta.get("sample_rate") != FS:
            raise ValueError("Formato ou frequência incompatível.")
        names = ("raw", "times", "quality", "lead_modes") if meta["version"] == 2 else ("raw", "times", "quality")
        expected = {"metadata.json", *(name + ".npy" for name in names)}
        if set(archive.namelist()) != expected or len(archive.infolist()) != len(expected):
            raise ValueError("Estrutura de gravação inválida.")
        arrays = {}
        for name in names:
            data = archive.read(name + ".npy")
            if hashlib.sha256(data).hexdigest() != meta.get("hashes", {}).get(name + ".npy"):
                raise ValueError("O arquivo falhou na verificação de integridade.")
            arrays[name] = np.load(io.BytesIO(data), allow_pickle=False)
    raw, times, quality = (arrays[k] for k in ("raw", "times", "quality"))
    n = len(raw)
    if raw.shape != (n, 2) or raw.dtype != np.int16 or not 0 < n <= FS * 660:
        raise ValueError("Amostras inválidas.")
    if times.shape != (n,) or quality.shape != (n,) or quality.dtype != bool:
        raise ValueError("Tempos ou qualidade inválidos.")
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0) or times[0] < 0 or times[-1] > 3600:
        raise ValueError("Sequência temporal inválida.")
    factor = float(meta.get("mv_per_count", 0))
    if not 1e-8 <= factor <= 1:
        raise ValueError("Escala de amplitude inválida.")
    for key in ("start", "end"):
        if meta.get(key) is not None and not 0 <= float(meta[key]) <= times[-1] + 1:
            raise ValueError("Intervalo de gravação inválido.")
    if meta.get("start") is not None and meta.get("end") is not None and meta["start"] > meta["end"]:
        raise ValueError("Fim anterior ao início.")
    config = FilterConfig(**meta["filters"]).validate()
    result = Recording(bool(meta.get("synthetic")))
    result.raw[:n], result.times[:n], result.quality[:n] = raw, times, quality
    modes = arrays.get("lead_modes")
    if modes is None:
        modes = infer_modes(raw, times)
    if modes.shape != (n,) or modes.dtype != np.uint8 or not np.all(np.isin(modes, (0, 1, 6))):
        raise ValueError("Disponibilidade de derivações inválida.")
    available = channel_available(raw)
    if np.any((modes > 0) & ~available[:, 0]) or np.any((modes == 6) & ~available.all(axis=1)):
        raise ValueError("Derivações incompatíveis com os marcadores de contato.")
    result.lead_modes[:n] = modes
    result.n, result.meta = n, meta
    stored_profile = meta.get("operational_profile")
    if stored_profile is not None:
        if not isinstance(stored_profile, dict) or stored_profile.get("schema") != 1:
            raise ValueError("Perfil operacional invalido.")
        set_profile(result, stored_profile.get("id"))
    result.configure(config)
    result.gaps = int(np.sum(np.diff(times) > 0.12))
    return result
