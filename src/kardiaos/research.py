"""Local experimental analysis contracts. Importing this module never loads ML models."""
from pathlib import Path
import io
import json
import os
import subprocess
import sys
import numpy as np

CATALOG_PATH = Path(__file__).parent / 'assets' / 'research_catalog.json'


def catalog():
    return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))


def runtime_config():
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    path = root / 'research-runtime.json'
    if not path.is_file():
        raise ValueError('Ambiente de pesquisa não configurado. Execute scripts/setup_research.py conforme o README.')
    cfg = json.loads(path.read_text(encoding='utf-8'))
    if not Path(cfg['python']).is_file() or not Path(cfg['models_dir']).is_dir():
        raise ValueError('Ambiente de pesquisa ou pasta de pesos não está disponível.')
    return cfg


def calibration_valid(recording):
    meta = recording.meta
    evidence = meta.get('research_calibration', {})
    return (meta.get('amplitude_verified') is True
            and evidence.get('polarity_verified') is True
            and isinstance(evidence.get('reference'), str)
            and len(evidence['reference'].strip()) >= 8
            and evidence.get('mv_per_count') == meta.get('mv_per_count'))


def inspect_window(recording, model_key, offset=0.0):
    model = catalog()['models'][model_key]
    result = {'model': model_key, 'name': model['name'], 'status': 'inconclusive',
              'reasons': [], 'scores': [], 'synthetic': bool(recording and recording.meta.get('synthetic'))}
    reasons = result['reasons']
    if recording is None or not recording.n or recording.meta.get('start') is None:
        reasons.append('Abra ou conclua uma captura com trecho estabilizado.')
        return result
    r = recording
    if r.meta.get('sample_rate') != 300:
        reasons.append('Frequência incompatível; esta integração aceita 300 Hz nominais.')
    if not np.isfinite(offset) or offset < 0:
        reasons.append('Início do trecho inválido.')
        return result
    if not result['synthetic'] and not calibration_valid(r):
        reasons.append('Escala e/ou polaridade não verificadas com referência documentada. Não são emitidos scores.')
    factor = r.meta.get('mv_per_count', 0)
    if not isinstance(factor, (int, float)) or not np.isfinite(factor) or factor <= 0:
        reasons.append('Fator de amplitude inválido.')
    begin = float(r.meta['start']) + float(offset)
    left = int(np.searchsorted(r.times[:r.n], begin, side='left'))
    right = left + 3000
    end = float(r.meta.get('end') or r.last_time) + 1 / 300
    result.update(first_sample=left, last_sample=right, offset_seconds=float(offset), duration_seconds=10,
                  input_sample_rate=300, model_sample_rate=500, leads=model['leads'],
                  calibration_verified=calibration_valid(r))
    if right > r.n or left >= r.n or r.times[min(right - 1, r.n - 1)] >= end:
        reasons.append('O trecho selecionado precisa conter 10 s completos; não há preenchimento artificial.')
        return result
    times = r.times[left:right]
    if not np.allclose(np.diff(times), 1 / 300, rtol=0, atol=1e-6):
        reasons.append('Há lacuna de transporte no trecho; selecione outra janela contínua.')
    if not r.quality[left:right].all():
        reasons.append('O trecho contém amostras sem qualidade/contato aceitos.')
    modes = r.lead_modes[left:right]
    if not np.all(modes >= (1 if len(model['leads']) == 1 else 6)):
        reasons.append('Derivações necessárias indisponíveis no trecho: ' + ', '.join(model['leads']) + '.')
    channels = 1 if len(model['leads']) == 1 else 2
    raw = r.raw[left:right, :channels]
    if np.any((raw & 3) != 0):
        reasons.append('Marcadores M2 indicam perda de contato.')
    if np.any(np.std(raw.astype(float), axis=0) < 3) or np.any(np.abs(raw.astype(float)) >= 32760):
        reasons.append('Sinal constante ou saturado.')
    if not reasons:
        result['status'] = 'ready'
    return result


def analyze(recording, model_key, offset=0.0):
    result = inspect_window(recording, model_key, offset)
    if result['status'] != 'ready':
        return result
    try:
        cfg = runtime_config()
        left, right = result['first_sample'], result['last_sample']
        values = recording.lead_values(left, right, raw=True)[:, :len(result['leads'])].T.copy()
        payload = io.BytesIO()
        np.savez(payload, values_mv=values, model_key=np.array(model_key))
        worker = Path(__file__).with_name('research_worker.py')
        if getattr(sys, 'frozen', False):
            worker = Path(sys.executable).parent / 'source' / 'src' / 'kardiaos' / 'research_worker.py'
        env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg')
        # The request is anonymous numeric data over local process pipes, never a network request.
        process = subprocess.run([cfg['python'], '-I', str(worker), '--models', cfg['models_dir']],
                                 input=payload.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=180, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if process.returncode:
            raise ValueError('Falha no processo local de pesquisa. Verifique instalação e integridade dos pesos.')
        response = json.loads(process.stdout.decode('utf-8'))
        if response.get('status') != 'ok':
            raise ValueError(response.get('reason', 'Modelo indisponível.'))
        labels = catalog()['models'][model_key]['labels']
        scores = np.asarray(response.get('scores'), dtype=float)
        if scores.shape != (len(labels),) or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
            raise ValueError('Saída incompatível com o mapeamento verificado de rótulos.')
        result.update(status='synthetic' if result['synthetic'] else 'experimental', reasons=[],
                      scores=[dict(label, score=float(score)) for label, score in zip(labels, scores)],
                      checkpoint_sha256=response['checkpoint_sha256'], runtime=response['runtime'],
                      elapsed_seconds=response['elapsed_seconds'], preprocessing=response['preprocessing'],
                      interpretation='Scores sigmoid não calibrados. Sem validação clínica no KardiaMobile. Não são diagnósticos.')
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        result.update(status='inconclusive', reasons=[str(exc)], scores=[])
    return result
