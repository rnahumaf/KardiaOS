"""Isolated CPU inference worker. Reads/writes local pipes; no download/network code."""
from pathlib import Path
from collections import OrderedDict
import argparse
import hashlib
import io
import json
import sys
import time


def run(models_dir, payload):
    import numpy as np
    import torch
    from easydict import EasyDict
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    from research_preprocess import preprocess
    assets = json.loads((here / 'assets' / 'research_catalog.json').read_text(encoding='utf-8'))
    with np.load(io.BytesIO(payload), allow_pickle=False) as request:
        key = str(request['model_key'])
        x = request['values_mv'].copy()
    spec = assets['models'][key]
    checkpoint = Path(models_dir) / spec['filename']
    if not checkpoint.is_file():
        raise ValueError('Checkpoint oficial não instalado: ' + spec['filename'])
    with checkpoint.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != spec['sha256']:
        raise ValueError('O checkpoint não corresponde ao SHA-256 verificado. Nenhuma inferência foi executada.')
    torch.set_num_threads(4)
    # Permit only known data containers, never unrestricted pickle or arbitrary checkpoint globals.
    allowed = [(OrderedDict, 'easydict.EasyDict'), np.dtype,
               np.dtypes.Float64DType, np.dtypes.Float32DType,
               (np._core.multiarray.scalar, 'numpy.core.multiarray.scalar')]
    started = time.perf_counter()
    with torch.serialization.safe_globals(allowed):
        ckpt = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if key == 'ecgfounder_1l':
        sys.path.insert(0, str(here / 'vendor' / 'ecgfounder'))
        from net1d import Net1D
        model = Net1D(in_channels=1, base_filters=64, ratio=1,
                      filter_list=[64,160,160,400,400,1024,1024],
                      m_blocks_list=[2,2,2,3,3,4,4], kernel_size=16, stride=2,
                      groups_width=16, verbose=False, use_bn=False, use_do=False, n_classes=150)
        state = ckpt['state_dict']
        if tuple(state['dense.weight'].shape) != (150, 1024) or len(spec['labels']) != 150:
            raise ValueError('Cabeça ECGFounder ou rótulos incompatíveis.')
    else:
        sys.path.insert(0, str(here / 'vendor' / 'deeppsp'))
        from torch_ecg_bak.torch_ecg.models.ecg_crnn import ECG_CRNN
        cfg = ckpt['train_config']
        if (list(cfg['leads']) != spec['leads'] or cfg['fs'] != 500
                or list(cfg['classes']) != [label['abbreviation'] for label in spec['labels']]
                or cfg['bandpass'] != [0.5, 60] or cfg['bandpass_order'] != 5
                or cfg['normalize_data'] is not True):
            raise ValueError('Contrato de entrada/saída DeepPSP incompatível com o checkpoint.')
        model = ECG_CRNN(cfg['classes'], cfg['n_leads'], EasyDict(ckpt['model_config']))
        state = ckpt['model_state_dict']
    model.load_state_dict(state, strict=True)
    model.eval()
    values = preprocess(x, key)
    with torch.inference_mode():
        scores = torch.sigmoid(model(torch.from_numpy(values)[None])).numpy()[0]
    if scores.shape != (len(spec['labels']),) or not np.isfinite(scores).all():
        raise ValueError('O modelo não retornou scores finitos com a dimensão esperada.')
    return dict(status='ok', scores=scores.tolist(), checkpoint_sha256=digest,
                runtime='PyTorch ' + torch.__version__ + ' / CPU',
                elapsed_seconds=round(time.perf_counter() - started, 3), preprocessing=spec['preprocessing'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', required=True)
    args = parser.parse_args()
    try:
        payload = sys.stdin.buffer.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError('Entrada maior que o limite de uma janela.')
        # Keep stdout a JSON protocol even if an imported library writes diagnostics.
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            result = run(args.models, payload)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else 'Falha local: ' + type(exc).__name__
        result = dict(status='inconclusive', reason=reason, scores=[])
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8'))
