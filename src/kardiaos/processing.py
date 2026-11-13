"""Explicit operational assumptions, independent of reviewed acquisition evidence."""
import copy
import math
import numpy as np
from .signal import FilterConfig

EMPIRICAL = 'research-empirical-v1'
REFERENCED = 'referenced'
DEFAULT_FILTERS = FilterConfig(.5, 40, 60)


def profile_id(recording):
    return getattr(recording, 'processing_profile_id', REFERENCED)


def empirical(recording):
    return recording is not None and profile_id(recording) == EMPIRICAL


def set_profile(recording, identifier):
    if identifier not in (EMPIRICAL, REFERENCED):
        raise ValueError('Perfil de processamento desconhecido.')
    recording.processing_profile_id = identifier
    # This changes the operational view, never raw samples or evidence metadata.
    recording._automatic_analysis = None


def scale_and_signs(recording):
    from .orientation import evidence_state
    base = float(recording.meta['mv_per_count'])
    if not math.isfinite(base) or base <= 0:
        raise ValueError('Escala de amplitude invalida.')
    if empirical(recording):
        return base * 1.5, (1, 1)
    state = evidence_state(recording)
    return base, tuple(state['decoder'][v] or 1 for v in ('I', 'II'))


def profile_info(recording):
    if recording is None:
        return dict(id=REFERENCED, schema=1)
    factor, signs = scale_and_signs(recording)
    return dict(schema=1, id=profile_id(recording), version=1,
                status='assumed_empirical' if empirical(recording) else 'evidence_gated',
                amplitude_multiplier=1.5 if empirical(recording) else 1.,
                base_mv_per_count=float(recording.meta['mv_per_count']), effective_mv_per_count=factor,
                raw_multipliers=list(signs), filters=recording.config.to_dict(),
                input_stage='display_filtered' if empirical(recording) else 'raw',
                calibration_claim=False,
                method='Common positive empirical gain; no score-based polarity selection; model-specific preprocessing follows.')


def profile_label(recording):
    return 'Pesquisa estimada | sinal preservado | ganho empirico 1,5' if empirical(recording) else 'Referencia por canal'


def snapshot(recording):
    """An in-memory immutable job input; not a disk copy or rollback file."""
    if recording is None:
        return None
    result = copy.copy(recording)
    result.meta = copy.deepcopy(recording.meta)
    result._analysis_cache = copy.deepcopy(getattr(recording, '_analysis_cache', {}))
    result._automatic_analysis = copy.deepcopy(getattr(recording, '_automatic_analysis', None))
    for name in ('raw', 'filtered', 'times', 'quality', 'lead_modes'):
        value = getattr(recording, name)[:recording.n].copy()
        value.flags.writeable = False
        setattr(result, name, value)
    return result


def scope(recording, offset=0., duration=None):
    if not math.isfinite(offset) or offset < 0 or duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ValueError('Janela de analise invalida.')
    if recording is None or not recording.n or recording.meta.get('start') is None:
        return dict(offset_seconds=float(offset), duration_seconds=0.)
    end = min(recording.last_time, float(recording.meta.get('end') or recording.last_time)) + 1 / 300
    remaining = max(0., end - float(recording.meta['start']) - offset)
    return dict(offset_seconds=float(offset), duration_seconds=min(remaining, 30. if duration is None else float(duration)))


def model_values(recording, key, first, last, signs=None):
    from .signal import six_leads
    count = 1 if key == 'ecgfounder_1l' else 2
    if empirical(recording) and signs is None:
        # Exactly the source used by the display/report; the worker then applies its pinned contract.
        values = recording.lead_values(first, last, raw=False)
        return values[:, :1 if count == 1 else 6 if key == 'deeppsp_6l' else 2].T.copy()
    if signs is None:
        from .orientation import normal_signs
        signs = normal_signs(recording, key)
    x = recording.raw[first:last, :count].astype(float) * np.asarray(signs)
    if key == 'deeppsp_6l':
        x = six_leads(x)
    return x.T * scale_and_signs(recording)[0]
