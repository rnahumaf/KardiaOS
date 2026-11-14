"""Reproduce frozen per-lead LUDB timing evaluation; local public data only.

Install optional validation dependencies from requirements-validation.txt.
This evaluates the candidate engine. Release QT/QTc remain withheld by policy.
No network calls, no datasets or personal results are bundled with the app.
"""
from pathlib import Path
import argparse,collections,hashlib,importlib.util,json,sys
import numpy as np,wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kardiaos.recording import Recording
from kardiaos.measurement_engine import measure_recording
from kardiaos.delineation import detect
from kardiaos.processing import set_profile,EMPIRICAL,DEFAULT_FILTERS
KEYS={'qrs_duration':('qon','qoff'),'p_duration':('pon','poff'),'qt':('qon','toff')}
DATA=None
def references(ident,lead):
    a=wfdb.rdann(str(DATA/str(ident)),lead);waves=[]
    for j,sym in enumerate(a.symbol):
        if sym in ['N','p','t']:
            wave=dict(kind=sym,peak=a.sample[j]/500)
            if j>0 and a.symbol[j-1]=='(':wave['on']=a.sample[j-1]/500
            if j+1<len(a.symbol) and a.symbol[j+1]==')':wave['off']=a.sample[j+1]/500
            waves.append(wave)
    beats=[]
    qrs=[w for w in waves if w['kind']=='N']
    for j,q in enumerate(qrs):
        if not .6<=q['peak']<=9.4:continue
        b=dict(r=q['peak'])
        if 'on' in q:b['qon']=q['on']
        if 'off' in q:b['qoff']=q['off']
        p=[w for w in waves if w['kind']=='p' and q['peak']-.4<w['peak']<q.get('on',q['peak'])]
        t=[w for w in waves if w['kind']=='t' and q.get('off',q['peak'])<w['peak']<min(q['peak']+.65,qrs[j+1].get('on',qrs[j+1]['peak']) if j+1<len(qrs) else 10)]
        if len(p)==1:
            if 'on' in p[0]:b['pon']=p[0]['on']
            if 'off' in p[0]:b['poff']=p[0]['off']
        if len(t)==1:
            if 'on' in t[0]:b['ton']=t[0]['on']
            if 'off' in t[0]:b['toff']=t[0]['off']
        beats.append(b)
    return beats


def score(pred,refs,metrics):
    interior=[p for p in pred if refs and refs[0]['r']-.1<=p['r']/300<=refs[-1]['r']+.1]
    output={'excluded_edge_detections':len(pred)-len(interior),'reference_beats':len(refs),'detected_beats':len(interior),'matched':0,'record_errors':{},'wave_errors':{},'counts':{}}
    pred=interior
    used=set();matches=[]
    for p in pred:
        available=[j for j in range(len(refs)) if j not in used and abs(refs[j]['r']-p['r']/300)<=.1]
        if available:
            j=min(available,key=lambda k:abs(refs[k]['r']-p['r']/300));used.add(j);matches.append((p,refs[j]))
    output['matched']=len(matches)
    for key,(on,off) in KEYS.items():
        truth=[(b[off]-b[on])*1000 for b in refs if on in b and off in b]
        errors=[(p[off]-p[on])/300*1000-(r[off]-r[on])*1000 for p,r in matches if all(k in p and k in r for k in [on,off])]
        output['wave_errors'][key]=errors
        output['counts'][key]={'references':len(truth),'outputs':sum(on in b and off in b for b in pred),'matched_outputs':len(errors)}
        if truth and key in metrics:output['record_errors'][key]=metrics[key]-float(np.median(truth))
    if len(refs)>1 and 'heart_rate' in metrics:
        output['record_errors']['heart_rate']=metrics['heart_rate']-float(60/np.median(np.diff([b['r'] for b in refs])))
    return output


def stats(values):
    a=np.asarray(values,dtype=float)
    return dict(n=len(a),bias=float(np.mean(a)) if len(a) else None,mae=float(np.mean(abs(a))) if len(a) else None,
        p90_abs=float(np.percentile(abs(a),90)) if len(a) else None,max_abs=float(np.max(abs(a))) if len(a) else None)


def summary(rows):
    out={}
    for method in sorted({r['method'] for r in rows}):
      out[method]={}
      for lead in ['i','ii']:
        selected=[r for r in rows if r['method']==method and r['lead']==lead]
        d=dict(records=len(selected),subjects=len({r['ident'] for r in selected}))
        tp=sum(r['matched'] for r in selected);total=sum(r['reference_beats'] for r in selected);det=sum(r['detected_beats'] for r in selected)
        d['candidate_detector']=dict(sensitivity=tp/total,ppv=tp/max(1,det),matched=tp,reference=total,detected=det,excluded_edges=sum(r['excluded_edge_detections'] for r in selected))
        for key,mae,p90 in [('heart_rate',2,5),('p_duration',20,40),('qrs_duration',15,35),('qt',25,50)]:
            eligible=[r for r in selected if r['eligible'][key]]
            accepted=[r for r in eligible if key in r['record_errors']]
            values=[r['record_errors'][key] for r in accepted]
            st=stats(values);st.update(eligible_records=len(eligible),accepted_records=len(accepted),coverage=len(accepted)/max(1,len(eligible)),all_record_outputs=sum(key in r['metrics'] for r in selected),outputs_without_eligible_reference=sum(key in r['metrics'] and not r['eligible'][key] for r in selected))
            st['beats']=dict(errors=stats([e for r in selected for e in r['wave_errors'].get(key,[])]),references=sum(r['counts'].get(key,{}).get('references',0) for r in selected),outputs=sum(r['counts'].get(key,{}).get('outputs',0) for r in selected),matched_outputs=sum(r['counts'].get(key,{}).get('matched_outputs',0) for r in selected))
            st['release_target_passed']=bool(st['n'] and st['mae']<=mae and st['p90_abs']<=p90 and st['coverage']>=.5 and d['candidate_detector']['sensitivity']>=.95 and d['candidate_detector']['ppv']>=.95)
            d[key]=st
        d['boundaries']={key:stats([e for r in selected for e in r['boundary_errors'].get(key,[])]) for key in ['qon','qoff','pon','poff','toff']}
        d['abstentions']={key:dict(collections.Counter(r['reasons'][key] for r in selected if key not in r['metrics'])) for key in ['heart_rate','p_duration','qrs_duration','qt']}
        out[method][lead]=d
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True,help='LUDB 1.0.1 directory containing data/ and SHA256SUMS.txt')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--split',choices=['development','held_out'],default='held_out')
    parser.add_argument('--baseline-source',type=Path,help='Optional original 0.6.0 measurements.py for comparison')
    parser.add_argument('--baseline-profile',choices=['referenced','empirical'],default='empirical')
    args=parser.parse_args()
    global DATA
    DATA=args.data/'data'
    checked=0
    for line in (args.data/'SHA256SUMS.txt').read_text().splitlines():
        sha,name=line.split(maxsplit=1);p=(args.data/name.lstrip('*')).resolve()
        if not p.is_relative_to(args.data.resolve()):raise ValueError('Invalid checksum path')
        if p.is_file():
            if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Dataset checksum mismatch')
            checked+=1
    order=np.random.default_rng(1729).permutation(np.arange(1,201))
    ids=sorted((order[:40] if args.split=='development' else order[40:]).tolist())
    old=None
    if args.baseline_source:
        spec=importlib.util.spec_from_file_location('kardiaos.baseline_measurements',args.baseline_source)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=[]
    for ident in ids:
        public=wfdb.rdrecord(str(DATA/str(ident)),channels=[0,1])
        for ch,lead in enumerate(['i','ii']):
            x=resample_poly(public.p_signal[:,ch],3,5);raw=np.round(x*4096/4)*4
            if np.max(abs(raw))>=32760:raise ValueError('Test adapter would saturate; never wrap')
            r=Recording(synthetic=True);r.append(0,np.column_stack([raw,raw]).astype(np.int16),True)
            r.meta.update(start=0.,end=r.last_time);r.lead_modes[:r.n]=6
            refs=references(ident,lead);peaks,_=detect(raw)
            for method in (['070','060'] if old else ['070']):
                if method=='060' and args.baseline_profile=='empirical':
                    set_profile(r,EMPIRICAL);r.configure(DEFAULT_FILTERS)
                measured=measure_recording(r,lead='I' if lead=='i' else 'II',include_other=False) if method=='070' else old.measure_recording(r)
                metrics={k:v['value'] for k,v in measured['metrics'].items() if v['value'] is not None}
                pred=[dict(r=int(v)) for v in peaks];points={v['r']:v for v in measured.get('fiducials',[])}
                for v in pred:
                    found=points.get(v['r'],{})
                    for key,on,off in [('qrs_duration','qon','qoff'),('p_duration','pon','poff'),('qt','qon','toff')]:
                        if key in metrics and on in found and off in found:v.update({on:found[on],off:found[off]})
                scored=score(pred,refs,metrics);be={k:[] for k in ['qon','qoff','pon','poff','toff']};used=set()
                for v in pred:
                    candidates=[j for j,ref in enumerate(refs) if j not in used and abs(v['r']/300-ref['r'])<=.1]
                    if not candidates:continue
                    j=min(candidates,key=lambda j:abs(v['r']/300-refs[j]['r']));used.add(j)
                    for key in be:
                        if key in v and key in refs[j]:be[key].append((v[key]/300-refs[j][key])*1000)
                eligible={'heart_rate':len(refs)>=5}
                for key,on,off in [('qrs_duration','qon','qoff'),('p_duration','pon','poff'),('qt','qon','toff')]:eligible[key]=sum(on in b and off in b for b in refs)>=3
                rows.append(dict(ident=ident,lead=lead,method=method,metrics=metrics,eligible=eligible,boundary_errors=be,reasons={k:v['reason'] for k,v in measured['metrics'].items()},**scored))
    digest={name:hashlib.sha256((ROOT/'src/kardiaos'/name).read_bytes()).hexdigest() for name in ['delineation.py','measurement_engine.py']}
    result=dict(dataset='LUDB 1.0.1',verified_files=checked,split=args.split,subjects=len(ids),seed=1729,engine_sha256=digest,
        baseline_profile=args.baseline_profile if old else None,summary=summary(rows))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
