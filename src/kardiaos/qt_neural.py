"""Original research adapter for trained CompactSegmenter; preserves raw sign."""
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
import sys,json,hashlib
import numpy as np,torch
from scipy.signal import resample_poly,welch
from .qt_network import CompactSegmenter
from scipy.signal import butter,sosfiltfilt
from . import delineation as dsp
from .qt_fiducials import analyze as tangent_analyze
WEIGHT_SHA256='41f0b6474a9769f59ba0be099412c665b49be0ab99f9d171b5de3704c7b73cd8'
WEIGHTS_PATH=None

def preprocess(x,fs=300):
    from math import gcd
    g=gcd(fs,300);x=resample_poly(np.asarray(x,float),300//g,fs//g)
    x=x-np.median(x)
    x=sosfiltfilt(butter(3,[.5,40],btype='bandpass',fs=300,output='sos'),x)
    return ((x-x.mean())/max(x.std(),1e-12)).astype(np.float32)


def runs(mask):
    d=np.diff(np.r_[False,mask,False].astype(int))
    return list(zip(np.flatnonzero(d==1),np.flatnonzero(d==-1)))

@lru_cache(maxsize=1)
def trained_model():
    if WEIGHTS_PATH is None:raise ValueError('Checkpoint QT não configurado.')
    path=Path(WEIGHTS_PATH)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=WEIGHT_SHA256:raise ValueError('Integridade do checkpoint QT inválida.')
    torch.set_num_threads(4);model=CompactSegmenter()
    model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True),strict=True)
    return model.eval()

def normalize(raw,fs):
    raw=np.asarray(raw,float)
    if raw.ndim!=1 or len(raw)<10*fs or not np.isfinite(raw).all():return None,'short_absent_or_nonfinite'
    raw=raw[:int(fs*10)]
    if raw.std()<1e-12:return None,'flat_signal'
    interior=raw[int(.6*fs):-int(.6*fs)]
    if any(b-a>=int(.5*fs) for a,b in runs(np.r_[False,np.diff(interior)==0])):return None,'flat_gap_or_clipping'
    from math import gcd
    g=gcd(300,fs);x=resample_poly(raw,300//g,fs//g);x=(x-np.median(x))/x.std()*1000
    f,p=welch(x,300,nperseg=1024)
    if p[f>=45].sum()/max(p[(f>=5)&(f<=40)].sum(),1e-12)>.5:return None,'high_frequency_noise'
    return x,''

def aggregate(result):
    values=dsp.aggregate(result);rr=np.asarray(result.get('rr',[]))
    qt=values.get('qt');qrs=values.get('qrs_duration')
    if qt is not None and qrs is not None and qrs<120 and len(rr)>=4 and .6<=np.median(rr)<=1.5 and np.std(rr)/np.mean(rr)<=.1:
        values['qtc_f']=float(qt/np.cbrt(np.median(rr)))
    scores=[b['score'] for b in result['beats'] if 'toff' in b]
    result.update(metrics=values,score=min(scores) if scores and qt is not None else None,reason='' if qt is not None else 'window_quality_or_dispersion')
    return result

def analyze(raw,fs=300):
    x,why=normalize(raw,fs)
    if x is None:return {n:dict(metrics={},beats=[],score=None,rr=[],reason=why) for n in ('neural','hybrid','tangent')}
    r=dsp.delineate(x);tangent=tangent_analyze(x,'tangent');tangent['score']=None
    neural=deepcopy(r)
    with torch.no_grad():
        inp=torch.from_numpy(preprocess(x,300))[None,None]
        prob=trained_model()(inp).softmax(1)[0].numpy().T
    mask=prob.argmax(-1)==3
    for a,b in runs(~mask):
        if 0<a<b<len(mask) and b-a<=2:mask[a:b]=True
    segments=runs(mask)
    for i,b in enumerate(neural['beats']):
        b.pop('ton',None);b.pop('toff',None);b['reason']['t']='QRS_anchor_missing'
        if 'qon' not in b or i+1==len(neural['beats']) or 'qon' not in neural['beats'][i+1]:continue
        nxt=neural['beats'][i+1]['qon']
        options=[(a,z) for a,z in segments if a>b['qoff'] and z<=nxt-12 and z-a>=10]
        if len(options)!=1:b['reason']['t']='T_absent_or_multiple_segments';continue
        a,z=options[0];end=z-1
        if not .2<(end-b['qon'])/300<.6:b['reason']['t']='QT_technical_range';continue
        b['toff']=int(end);b['score']=float(np.percentile(prob[a:z,3],10));b['reason']['t']=''
    neural=aggregate(neural);hybrid=deepcopy(neural)
    for b,t in zip(hybrid['beats'],tangent['beats']):
        if 'toff' in b and ('toff' not in t or abs(b['toff']-t['toff'])/300>.030):
            b.pop('toff');b.pop('score',None);b['reason']['t']='tangent_disagreement_or_missing'
    return dict(neural=neural,hybrid=aggregate(hybrid),tangent=tangent)
