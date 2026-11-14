"""Lead-specific research timing using Gaussian derivative scales and prominence.

Independent implementation inspired by slope/multiscale principles in Martinez
et al., IEEE TBME 2004, doi:10.1109/TBME.2003.821031, and prominence concepts
in Emrich et al., EUSIPCO 2024, doi:10.23919/EUSIPCO63174.2024.10715353.
Not a reproduction of either published algorithm or its reported accuracy.
See docs/measurement-validation.md for selection, testing and limitations.
"""
import numpy as np
from scipy.signal import butter,sosfiltfilt,find_peaks,iirnotch,filtfilt
from scipy.ndimage import uniform_filter1d,gaussian_filter1d
FS=300
METHOD_VERSION='timing-dsp-1'
PIPELINE=dict(id=METHOD_VERSION, source='raw', sample_rate_hz=300,
    highpass_hz=.5, highpass_order=2, lowpass_hz=80., lowpass_order=2,
    phase='forward-backward zero phase', notch_hz=None,
    qrs_gaussian_sigma_samples=2.5, pt_gaussian_sigma_samples=3.,
    polarity='sign-invariant timing; recorded trace is never inverted',
    amplitude='relative contrast; no absolute mV thresholds',
    display_pipeline=False, resolution_ms=1000/FS)

def preprocess(raw,hp=.5,notch=False):
    x=np.asarray(raw,dtype=float)-np.median(raw)
    if hp:
        x=sosfiltfilt(butter(2,hp,btype='highpass',fs=FS,output='sos'),x)
        x=sosfiltfilt(butter(2,80,btype='lowpass',fs=FS,output='sos'),x)
    if notch:x=filtfilt(*iirnotch(60,30,fs=FS),x)
    return x

def detect(raw):
    x=sosfiltfilt(butter(3,[5,25],btype='bandpass',fs=FS,output='sos'),raw)
    energy=uniform_filter1d(np.gradient(x)**2,24)
    candidates=[]
    for frac in [.12,.25]:
        p,_=find_peaks(energy,distance=84,prominence=frac*np.percentile(energy,99))
        refined=[]
        for v in p:
            if v<180 or v>=len(x)-180:continue
            q=int(v-24+np.argmax(abs(x[v-24:v+25])))
            if not refined or q-refined[-1]>=75:refined.append(q)
        candidates.append(np.array(refined,dtype=int))
    a,b=candidates
    stable=len(a)>=5 and len(a)==len(b) and np.max(abs(a-b))<=9
    return a, bool(stable)



def slope_bounds(x,lo,hi,anchor,kind,noise,qamp):
    if hi-lo<12:return None,'short_window'
    sigma=2.5 if kind=='qrs' else 3.
    smooth=gaussian_filter1d(x,sigma);d=np.gradient(smooth)
    local=smooth[lo:hi];deriv=d[lo:hi]
    if kind=='qrs':
        env=uniform_filter1d(abs(deriv),3)
        mid=anchor-lo; main=max(env[max(0,mid-12):mid+13])
        limits=[]
        for frac in [.05,.10]:
            threshold=max(frac*main,noise/4)
            above=env>threshold
            # A 10-ms quiet run separates the QRS from adjacent activity.
            left=right=None
            for j in range(mid-3,1,-1):
                if not above[j:j+3].any():left=j+3;break
            for j in range(mid+1,len(local)-4):
                if not above[j:j+3].any():right=j;break
            if left is None or right is None:return None,'boundary_at_edge'
            limits.append((lo+left,lo+right))
    else:
        baseline=np.linspace(np.median(local[:3]),np.median(local[-3:]),len(local))
        local=local-baseline;deriv=deriv-(baseline[1]-baseline[0])
        candidates=[]
        for sign in [1,-1]:
            peaks,prop=find_peaks(sign*local,prominence=max(6*noise,.03*qamp if kind=='p' else .05*qamp))
            candidates.extend((int(p),sign,float(v)) for p,v in zip(peaks,prop['prominences']))
        if not candidates:return None,'low_contrast'
        peak,sign,prom=max(candidates,key=lambda v:v[2])
        if any(s!=sign and s*local[p]>.4*abs(local[peak]) and v>.4*prom and abs(p-peak)<.15*FS for p,s,v in candidates):
            return None,'biphasic_or_adjacent'
        width=int((.10 if kind=='p' else .17)*FS)
        lower=max(1,peak-width);upper=min(len(local)-2,peak+width)
        if peak<=lower+2 or peak>=upper-2:return None,'boundary_at_edge'
        l=lower+int(np.argmax(sign*deriv[lower:peak]));r=peak+int(np.argmax(-sign*deriv[peak:upper]))
        if sign*deriv[l]<=0 or -sign*deriv[r]<=0:return None,'unclosed_wave'
        limits=[]
        for frac in [.3,.5]:
            left=l;right=r
            while left>1 and sign*deriv[left]>frac*sign*deriv[l]:left-=1
            while right<len(local)-2 and -sign*deriv[right]>frac*-sign*deriv[r]:right+=1
            if left<=1 or right>=len(local)-2:return None,'boundary_at_edge'
            limits.append((lo+left,lo+right))
    if max(abs(limits[0][j]-limits[1][j]) for j in [0,1])>6:return None,'threshold_unstable'
    on,off=np.rint(np.mean(limits,axis=0)).astype(int)
    low,high={'qrs':(.04,.25),'p':(.04,.2),'t':(.07,.4)}[kind]
    if not low+1/FS<(off-on)/FS<high-1/FS:return None,'duration_limit'
    if kind=='qrs' and not on<anchor<off:return None,'anchor_outside'
    return (int(on),int(off)),''

def delineate(raw,hp=.5,notch=False):
    raw=np.asarray(raw,dtype=float)
    if raw.ndim!=1 or len(raw)<FS*10 or not np.isfinite(raw).all() or np.std(raw)<1e-12:
        return dict(peaks=[],stable=False,beats=[],noise=0.,rr=[])
    x=preprocess(raw,hp,notch);peaks,stable=detect(raw)
    if len(peaks)<2:
        return dict(peaks=peaks.tolist(),stable=False,beats=[dict(r=int(p),reason={}) for p in peaks],noise=0.,rr=[])
    high=x-gaussian_filter1d(x,1.)
    noise=float(np.median(abs(high-np.median(high)))*1.4826)
    beats=[]
    rr=np.diff(peaks)/FS
    if len(peaks)>=5:
        snippets=np.stack([x[p-45:p+46] for p in peaks]);snippets-=np.median(snippets[:,:8],axis=1)[:,None]
        template=np.median(snippets,axis=0);centered=snippets-snippets.mean(axis=1)[:,None];tc=template-template.mean()
        correlations=(centered@tc)/np.maximum(np.linalg.norm(centered,axis=1)*np.linalg.norm(tc),1e-20)
        stable=stable and np.median(correlations)>=.8 and np.ptp(template)>=8*max(noise,1e-10)
    for i,r in enumerate(peaks):
        beat={'r':int(r),'reason':{}}
        qamp=float(np.ptp(x[r-45:r+46]))
        q,why=slope_bounds(x,r-45,r+46,r,'qrs',noise,qamp)
        beat['reason']['qrs']=why
        if q:
            beat.update(qon=q[0],qoff=q[1])
            prev=peaks[i-1] if i else r-int(np.median(np.diff(peaks)))
            nxt=peaks[i+1] if i+1<len(peaks) else r+int(np.median(np.diff(peaks)))
            p_lo=max(r-105,prev+int(.55*(r-prev)));p_hi=q[0]-6
            p,why=slope_bounds(x,p_lo,p_hi,r,'p',noise,qamp);beat['reason']['p']=why
            if p:beat.update(pon=p[0],poff=p[1])
            t_lo=q[1]+9;t_hi=min(r+180,nxt-36)
            t,why=slope_bounds(x,t_lo,t_hi,r,'t',noise,qamp);beat['reason']['t']=why
            if t and .2<(t[1]-q[0])/FS<.6:beat.update(ton=t[0],toff=t[1])
        beats.append(beat)
    return {'peaks':peaks.tolist(),'stable':stable,'beats':beats,'noise':noise,'rr':rr.tolist()}

def aggregate(result):
    out={};beats=result['beats'];rr=np.asarray(result['rr'])
    if not result['stable'] or np.any((rr<.3)|(rr>2)):return out
    out['heart_rate']=float(60/np.median(rr))
    for name,on,off,maxiqr in [('qrs_duration','qon','qoff',20),('p_duration','pon','poff',20),('qt','qon','toff',30)]:
        values=[(v[off]-v[on])/FS*1000 for v in beats if on in v and off in v]
        delays=[(v[off]-v['r'])/FS*1000 for v in beats if on in v and off in v]
        stable_delay=not delays or name=='qrs_duration' or np.ptp(np.percentile(delays,[25,75]))<=(20 if name=='p_duration' else 40)
        if len(values)>=max(3,len(beats)*.5) and np.ptp(np.percentile(values,[25,75]))<=maxiqr and stable_delay:
            out[name]=float(np.median(values))
    return out
