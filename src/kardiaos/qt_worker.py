"""Local numeric IPC only; no downloads or remote inference."""
from pathlib import Path
import argparse,io,json,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from kardiaos import qt_neural

def safe(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--weights',required=True);args=parser.parse_args()
    qt_neural.WEIGHTS_PATH=Path(args.weights)
    with np.load(io.BytesIO(sys.stdin.buffer.read()),allow_pickle=False) as data:x=data['raw']
    if x.shape[0]!=3000 or x.ndim!=2 or x.shape[1] not in (1,2) or not np.isfinite(x).all():raise ValueError('Invalid input')
    leads=[qt_neural.analyze(x[:,ch])['neural'] for ch in range(x.shape[1])]
    print(json.dumps(dict(status='ok',checkpoint_sha256=qt_neural.WEIGHT_SHA256,leads=leads,
        method='CompactSegmenter082 + frozen DSP onset',confidence_calibrated=False),default=safe,allow_nan=False))

if __name__=='__main__':main()
