"""Technical validation only. Real captures are checked without overriding calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'src'))
from kardiaos.app import synthetic_pairs
from kardiaos.recording import Recording, load_recording
from kardiaos.research import analyze, catalog


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    summary={'synthetic':{}, 'captures':[], 'clinical_validation':False}
    r=Recording(synthetic=True)
    r.append(0,synthetic_pairs(0,3300),good=True)
    r.meta.update(start=1.0,end=r.last_time)
    for key in catalog()['models']:
        first=analyze(r,key)
        second=analyze(r,key)
        assert first['status']=='synthetic', first.get('reasons')
        a=np.array([v['score'] for v in first['scores']])
        b=np.array([v['score'] for v in second['scores']])
        np.testing.assert_allclose(a,b,rtol=0,atol=1e-7)
        summary['synthetic'][key]=dict(outputs=len(a), finite=bool(np.isfinite(a).all()), repeat_max_delta=float(np.max(abs(a-b))),
                                     elapsed_seconds=first['elapsed_seconds'], checkpoint_sha256=first['checkpoint_sha256'])
    for path in args.capture:
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        record=load_recording(path)
        results={key:analyze(record,key) for key in catalog()['models']}
        assert before == hashlib.sha256(path.read_bytes()).hexdigest(), 'Capture changed'
        # No signal, identifiers, dates, file names or diagnostic scores in the validation summary.
        summary['captures'].append({key:dict(status=value['status'], reasons=value['reasons'], scores_emitted=len(value['scores'])) for key,value in results.items()})
    if args.output:
        args.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
