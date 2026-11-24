"""Capture-local human review of the six global median landmarks."""
from datetime import datetime, timezone
import hashlib

import numpy as np
from .signal import FS


LABELS = {'pon': 'Início de P', 'poff': 'Fim de P', 'qon': 'Início do QRS',
          'qoff': 'Fim do QRS', 'ton': 'Início de T', 'toff': 'Fim de T'}


def median_identity(medians, centers, anchor, factor):
    digest = hashlib.sha256(b'KardiaOS-median-coordinates-v1')
    digest.update(np.asarray([FS, anchor], dtype='<i4').tobytes())
    digest.update(np.asarray(centers, dtype='<i4').tobytes())
    digest.update(np.asarray([factor], dtype='<f8').tobytes())
    for lead, waves in medians.items():
        digest.update(lead.encode('ascii'))
        for kind in ('qrs', 'pt'):
            digest.update(np.round(waves[kind], 8).astype('<f8').tobytes())
    return digest.hexdigest()


def validate_points(points, anchor, length):
    if not isinstance(points, dict) or any(k not in LABELS or type(v) is not int
            or not 0 <= v < length for k, v in points.items()):
        raise ValueError('Os marcos precisam estar dentro da curva exibida.')
    sequence = {**points, 'r': anchor}
    order = [k for k in ('pon', 'poff', 'qon', 'r', 'qoff', 'ton', 'toff') if k in sequence]
    for left, right in zip(order, order[1:]):
        if sequence[left] > sequence[right] or (sequence[left] == sequence[right]
                and (left, right) not in (('poff', 'qon'), ('qoff', 'ton'))):
            labels = {**LABELS, 'r': 'Referência R'}
            raise ValueError(f'{labels[left]} deve preceder {labels[right].lower()}.')


def review_state(recording, medians, centers, version, factor, automatic, anchor, sources):
    layout = 'di' if len(medians) == 1 else 'six'
    basis = median_identity(medians, centers, anchor, factor)
    length = len(medians['I']['qrs'])
    state = dict(layout=layout, basis=basis, origin='automatic', automatic_points=dict(automatic),
                 automatic_leads={k: item['supporting_leads'][0] for k, item in sources.items()},
                 anchor=anchor, length=length, leads=list(medians), method_version=version, notice='')
    reviews = recording.meta.get('landmark_reviews', {})
    saved = reviews.get(layout) if isinstance(reviews, dict) else None
    if saved is None:
        return state
    if not isinstance(saved, dict) or saved.get('schema') != 1 or saved.get('basis') != basis:
        state['notice'] = 'A revisão salva pertence a outra mediana. Os marcos desta análise são automáticos.'
        return state
    try:
        validate_points(saved.get('points'), anchor, length)
        leads = saved.get('point_leads')
        if (not isinstance(leads, dict) or set(leads) != set(saved['points'])
                or any(not isinstance(v, str) or v not in medians for v in leads.values())):
            raise ValueError('Derivação da revisão inválida.')
    except ValueError:
        state['notice'] = 'A revisão salva contém marcos inválidos. Os marcos desta análise são automáticos.'
        return state
    state['saved'] = saved
    if saved.get('active') is True:
        state['origin'] = 'manual'
    return state


def save_review(recording, state, points, point_leads):
    validate_points(points, state['anchor'], state['length'])
    if (not isinstance(point_leads, dict) or set(point_leads) != set(points)
            or any(not isinstance(v, str) or v not in state['leads'] for v in point_leads.values())):
        raise ValueError('Selecione uma derivação disponível para cada marco.')
    prior = recording.meta.get('landmark_reviews')
    reviews = dict(prior) if isinstance(prior, dict) else {}
    reviews[state['layout']] = dict(schema=1, basis=state['basis'], active=True, points=dict(points),
        point_leads=dict(point_leads), method_version=state['method_version'],
        reviewed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    recording.meta['landmark_reviews'] = reviews


def set_review_active(recording, state, active):
    saved = state.get('saved')
    if not saved:
        raise ValueError('Não há revisão compatível com a mediana atual.')
    reviews = dict(recording.meta['landmark_reviews'])
    reviews[state['layout']] = dict(saved, active=bool(active))
    recording.meta['landmark_reviews'] = reviews


def origin_label(measurement):
    state = measurement.get('landmark_review', {})
    if state.get('origin') == 'manual':
        return 'Marcos revisados manualmente'
    return 'Marcos automáticos, sem revisão manual (menor confiança)'
