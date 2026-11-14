"""Robust representative beats; original amplitude and sample time are preserved.

Research template083. Technical criteria are not calibrated confidence.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import butter,sosfiltfilt,welch
from . import delineation as dsp
from .qt_fiducials import endpoint,t_filter
FS=300
def input_reason(raw):
    x=np.asarray(raw,float)
    if x.ndim!=1 or len(x)!=3000 or not np.isfinite(x).all() or x.std()<1e-12:return 'missing_short_nonfinite_flat'
    interior=x[180:-180];flat=np.r_[False,np.diff(interior)==0,False]
    edge=np.diff(flat.astype(int));starts=np.flatnonzero(edge==1);ends=np.flatnonzero(edge==-1)
    if any(ends-starts>=150):return 'flat_gap_or_clipping'
    return ''

def corr(a,b):
    a=a-a.mean();b=b-b.mean();den=np.linalg.norm(a)*np.linalg.norm(b)
    return float(a@b/den) if den>1e-12 else -1.

def quality(raw):
    x=np.asarray(raw,float)
    why=input_reason(x)
    if why:return dict(eligible=False,score=-1.,reason=why)
    d=dsp.delineate((x-np.median(x))/x.std()*1000)
    if len(d['peaks'])<5:return dict(eligible=False,score=-1.,reason='insufficient_QRS')
    snippets=np.stack([x[p-45:p+46] for p in d['peaks']]);median=np.median(snippets,axis=0)
    repeat=float(np.median([corr(s,median) for s in snippets]))
    residual=x-gaussian_filter1d(x,1);noise=np.median(abs(residual-np.median(residual)))*1.4826
    contrast=float(np.ptp(median)/max(noise,1e-12))
    f,p=welch(x,FS,nperseg=1024);hf=float(p[f>=45].sum()/max(p[(f>=5)&(f<=40)].sum(),1e-20))
    eligible=bool(d['stable'] and hf<=.5 and contrast>=8)
    score=.4*max(0,repeat)+.4*min(1,np.log1p(contrast)/np.log(101))+.2/(1+hf)
    return dict(eligible=eligible,score=float(score) if eligible else -1.,qrs_repeatability=repeat,qrs_to_noise=contrast,hf_ratio=hf,reason='' if eligible else 'QRS_or_noise_quality')

def choose_lead(qualities):
    available=[(k,v) for k,v in qualities.items() if v['eligible']]
    return max(available,key=lambda kv:(kv[1]['score'],kv[0]=='I'))[0] if available else None

def single_qt(qx,tx,r,next_r,noise):
    qamp=float(np.ptp(qx[r-45:r+46]))
    q,why=dsp.slope_bounds(qx,r-45,r+46,r,'qrs',noise,qamp)
    if q is None:return dict(qt=None,reason='QRS_'+why)
    beat=dict(r=r,qon=q[0],qoff=q[1])
    end,why=endpoint(tx,np.gradient(tx),beat,next_r,noise,qamp,'tangent')
    if end is None:return dict(qt=None,reason='T_'+why,qon=q[0],qoff=q[1])
    return dict(qt=(end-q[0])/FS*1000,qrs=(q[1]-q[0])/FS*1000,qon=q[0],qoff=q[1],toff=end,reason='')

def build(raw):
    x=np.asarray(raw,float)
    why=input_reason(x)
    if why:return dict(groups=[],reason=why)
    d=dsp.delineate(x);peaks=d['peaks']
    if len(peaks)<5:return dict(groups=[],reason='insufficient_QRS')
    qx=dsp.preprocess(x);tx=t_filter(x)
    align=sosfiltfilt(butter(3,[5,25],btype='bandpass',fs=FS,output='sos'),x)
    high=qx-gaussian_filter1d(qx,1);noise=float(np.median(abs(high-np.median(high)))*1.4826)
    groups=[];eligible=[];rejected=[]
    for i,p in enumerate(peaks):
        if i==0 or i+1==len(peaks):continue
        prev=(p-peaks[i-1])/FS;nxt=(peaks[i+1]-p)/FS
        if p<99 or p+99>=len(x):continue
        amp=float(np.ptp(qx[p-45:p+46]))
        if amp<8*max(noise,1e-12):rejected.append(dict(beat=i,reason='QRS_contrast'));continue
        eligible.append(i);options=[]
        for j,g in enumerate(groups):
            if abs(prev/np.median(g['prev_rr'])-1)>.1 or abs(nxt/np.median(g['next_rr'])-1)>.1:continue
            if not .7<=amp/np.median(g['amps'])<=1.3:continue
            template=np.median(g['qrs_align'],axis=0)
            for lag in range(-9,10):
                rho=corr(align[p+lag-45:p+lag+46],template)
                if rho>=.95:options.append((rho,-abs(lag),-j,lag,j))
        if options:
            _,_,_,lag,j=max(options);g=groups[j]
        else:
            lag=0;g=dict(beat_indices=[],centers=[],shifts=[],prev_rr=[],next_rr=[],amps=[],qrs_align=[]);groups.append(g)
        g['beat_indices'].append(i);g['centers'].append(p+lag);g['shifts'].append(lag);g['prev_rr'].append(prev);g['next_rr'].append(nxt);g['amps'].append(amp);g['qrs_align'].append(align[p+lag-45:p+lag+46])
    output=[]
    for index,g in enumerate(groups):
        pre=min(90,int(.4*min(g['prev_rr'])*FS));post=min(195,int((min(g['next_rr'])-.12)*FS))
        if pre<48 or post<90:continue
        centers=g['centers'];n=len(centers)
        if any(p-pre<0 or p+post>=len(x) for p in centers):continue
        beats=np.stack([x[p-pre:p+post+1] for p in centers]);rawmed=np.median(beats,axis=0)
        qs=np.stack([qx[p-pre:p+post+1] for p in centers]);ts=np.stack([tx[p-pre:p+post+1] for p in centers])
        qm=np.median(qs,axis=0);tm=np.median(ts,axis=0)
        local_noise=max(noise/np.sqrt(max(n,1)),float(np.median(abs((qm-gaussian_filter1d(qm,1)))))*1.4826)
        next_r=pre+int(np.median(g['next_rr'])*FS)
        target=single_qt(qm,tm,pre,next_r,local_noise)
        individuals=[single_qt(q,t,pre,pre+int(rr*FS),noise) for q,t,rr in zip(qs,ts,g['next_rr'])]
        vals=[v['qt'] for v in individuals if v['qt'] is not None]
        a=pre+36;b=min(len(tm)-1,pre+165)
        tcurves=ts[:,a:b];tcurves=tcurves-np.linspace(tcurves[:,:3].mean(1),tcurves[:,-3:].mean(1),tcurves.shape[1]).T
        med=np.median(tcurves,axis=0);tamp=float(np.ptp(med));spread=float(np.percentile(np.median(abs(tcurves-med),axis=0),90)/max(tamp,1e-12))
        alternation=float(np.max(abs(np.median(tcurves[::2],axis=0)-np.median(tcurves[1::2],axis=0)))/max(tamp,1e-12)) if n>=6 else None
        qamp=float(np.ptp(qm[pre-45:pre+46]));reasons=[]
        if not d['stable']:reasons.append('unstable_QRS_detection')
        if n<5:reasons.append('fewer_than_5_similar_beats')
        if n<.5*len(eligible):reasons.append('minority_morphology_or_RR_group')
        if tamp<max(6*local_noise,.05*qamp):reasons.append('T_contrast_absent_or_low')
        if spread>.25:reasons.append('T_dispersion_blurring')
        if alternation is not None and alternation>.20:reasons.append('possible_T_alternation')
        t_signs=np.sign(tcurves[np.arange(n),np.argmax(abs(tcurves),axis=1)])
        if len(set(t_signs))>1:reasons.append('T_polarity_disagreement')
        if len(vals)<max(3,n*.5):reasons.append('individual_T_limits_insufficient')
        iqr=float(np.ptp(np.percentile(vals,[25,75]))) if vals else None
        if iqr is not None and iqr>20:reasons.append('individual_QT_dispersion')
        if target['qt'] is None:reasons.append(target['reason'])
        delta=target['qt']-float(np.median(vals)) if vals and target['qt'] is not None else None
        if delta is not None and abs(delta)>20:reasons.append('template_individual_disagreement')
        output.append(dict(group=index,n_beats=n,beat_indices=g['beat_indices'],original_r=[peaks[i] for i in g['beat_indices']],centers=centers,shift_samples=g['shifts'],
            prev_rr=g['prev_rr'],next_rr=g['next_rr'],sample_rate=FS,r_index=pre,time_seconds=(np.arange(len(rawmed))-pre)/FS,
            raw_beats=beats,raw_median=rawmed,raw_q25=np.percentile(beats,25,axis=0),raw_q75=np.percentile(beats,75,axis=0),
            measurement_t_median=tm,measurement_qrs_median=qm,
            candidate=target,individuals=individuals,individual_qt_iqr_ms=iqr,template_minus_individual_median_ms=delta,
            t_relative_spread=spread,t_odd_even_difference=alternation,technical_eligible=not reasons,reasons=reasons,
            amplitude_operation='none; original counts, pointwise median after integer translation',alignment='QRS translation only; no warping'))
    output.sort(key=lambda g:(-g['n_beats'],g['group']))
    return dict(groups=output,dominant_group=output[0]['group'] if output else None,eligible_beats=len(eligible),rejected=rejected,
        discarded_from_dominant=sum(g['n_beats'] for g in output[1:]),reason='' if output else 'no_supported_group')

def combine(group,model_result):
    reasons=list(group['reasons']);values=[]
    if model_result.get('metrics',{}).get('qt') is None:reasons.append('model_window_quality_or_dispersion')
    for r in group['original_r']:
        nearest=[b for b in model_result.get('beats',[]) if abs(b['r']-r)<=6 and 'toff' in b and 'qon' in b]
        if len(nearest)==1:values.append((nearest[0]['toff']-nearest[0]['qon'])/FS*1000)
    if len(values)<max(3,group['n_beats']*.5):reasons.append('model_group_limits_insufficient')
    model_qt=float(np.median(values)) if values else None
    if values and np.ptp(np.percentile(values,[25,75]))>20:reasons.append('model_QT_dispersion')
    qt=group['candidate']['qt']
    if model_qt is not None and qt is not None and abs(qt-model_qt)>20:reasons.append('model_template_disagreement')
    rr=np.asarray(group['next_rr']);qrs=group['candidate'].get('qrs')
    qtc=None
    if not reasons and qt is not None:
        if len(rr)<4 or not .6<=np.median(rr)<=1.5 or rr.std()/rr.mean()>.1 or qrs is None or qrs>=120:reasons.append('RR_or_QRS_precludes_QTc')
        else:qtc=float(qt/np.cbrt(np.median(rr)))
    return dict(qt_template=qt,qt_model_group_median=model_qt,qtc_f=qtc,technical_estimate=qtc is not None,reasons=reasons,
        rr_seconds=float(np.median(rr)),rr_cv=float(rr.std()/rr.mean()),formula_name='Fridericia',
        formula='QTcF = QT(ms) / RR(s)^(1/3)',calibrated_confidence=False,application_release_gate=False)

def label(lead,result):
    value=result.get('qtc_f') if result else None
    if value is None or not np.isfinite(value) or value<=0 or lead not in ('I','II'):return 'QTc: erro na estimativa'
    if result.get('formula_name')!='Fridericia' or not result.get('technical_estimate'):return 'QTc: erro na estimativa'
    return f'QTc: {int(round(value))} ms (D{lead}; Fridericia; baixa confiança)'
