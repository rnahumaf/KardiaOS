"""Original tangent endpoint, frozen research method; no clinical qualification."""
import numpy as np
from scipy.signal import butter,sosfiltfilt,find_peaks,welch
from scipy.ndimage import uniform_filter1d
from . import delineation as frozen
FS=300


def t_filter(raw):
    x=np.asarray(raw,float)-np.median(raw)
    x=sosfiltfilt(butter(4,.5,btype='highpass',fs=FS,output='sos'),x)
    return sosfiltfilt(butter(4,30,btype='lowpass',fs=FS,output='sos'),x)

def endpoint(x,d,beat,nxt,noise,qamp,method):
    r=beat['r'];lo=beat['qoff']+9;hi=min(r+180,nxt-45,len(x)-4)
    if hi-lo<24:return None,'short_T_window'
    segment=x[lo:hi]
    local=segment-np.linspace(np.median(segment[:3]),np.median(segment[-9:]),len(segment))
    candidates=[]
    for sign in (1,-1):
        peaks,p=find_peaks(sign*local,prominence=max(6*noise,.05*qamp))
        candidates += [(lo+int(j),sign,float(prom)) for j,prom in zip(peaks,p['prominences'])]
    if not candidates:return None,'low_T_contrast'
    main=max(candidates,key=lambda a:a[2]);peak,sign,prom=main
    other=[v for v in candidates if v!=main and v[2]>=.4*prom and abs(v[0]-peak)<=45]
    if len(other)>1:return None,'complex_TU_morphology'
    if other:
        second=other[0]
        if second[1]==sign and abs(second[0]-peak)>30:return None,'T_U_ambiguous'
        peak,sign,_=max([main,second],key=lambda a:a[0])
    last=min(peak+60,hi-1)
    if last-peak<6:return None,'terminal_slope_absent'
    xm=peak+int(np.argmax(-sign*d[peak:last]))
    if -sign*d[xm]<=max(noise/4,1e-12):return None,'terminal_slope_weak'
    a=peak+60;b=min(peak+120,nxt-60,r+195,len(x)-4)
    if b-a<9:return None,'no_TP_reference_window'
    quiet=uniform_filter1d(abs(d),9)
    xr=a+int(np.argmin(quiet[a:b]))
    if xr-xm<9:return None,'short_terminal_segment'
    if method=='tangent':
        fit=np.polyfit(np.arange(-2,3),x[xm-2:xm+3],1)
        slope=fit[0];baseline=float(np.median(x[xr-3:xr+4]))
        if -sign*slope<=max(noise/4,1e-12):return None,'tangent_slope_weak'
        end=xm+(baseline-fit[1])/slope
    else:
        ends=[]
        for anchor in (max(a,xr-4),xr,min(b-1,xr+4)):
            indices=np.arange(xm+1,anchor)
            if len(indices)<6:return None,'short_area_window'
            area=sign*(x[xm]-x[indices])*(2*anchor-indices-xm)
            ends.append(int(indices[np.argmax(area)]))
        if max(ends)-min(ends)>6:return None,'area_anchor_unstable'
        end=float(np.median(ends))
    if not np.isfinite(end) or end<=xm+1 or end>=xr-1:return None,'end_outside_terminal_segment'
    if not .2<(end-beat['qon'])/FS<.6:return None,'QT_technical_range'
    return int(np.rint(end)),''

def analyze(raw,method):
    raw=np.asarray(raw,float)
    if raw.ndim!=1 or len(raw)<FS*10 or not np.isfinite(raw).all() or np.std(raw)<3:
        return dict(method=method,beats=[],metrics={},reason='invalid_or_flat_input',rr=[])
    if np.max(abs(raw))>=32760:
        return dict(method=method,beats=[],metrics={},reason='adapter_saturation',rr=[])
    f,p=welch(raw,FS,nperseg=min(1024,len(raw)))
    if p[f>=45].sum()/max(p[(f>=5)&(f<=40)].sum(),1e-12)>.5:
        return dict(method=method,beats=[],metrics={},reason='high_frequency_noise',rr=[])
    result=frozen.delineate(raw)
    if method!='baseline070':
        peaks=result['peaks'];x=t_filter(raw);d=np.gradient(x)
        for i,beat in enumerate(result['beats']):
            beat.pop('ton',None);beat.pop('toff',None)
            if 'qon' not in beat:continue
            r=beat['r'];nxt=peaks[i+1] if i+1<len(peaks) else r+int(np.median(np.diff(peaks)))
            end,why=endpoint(x,d,beat,nxt,result['noise'],float(np.ptp(x[r-45:r+46])),method)
            if end is not None:beat['toff']=end
            beat['reason']['t']=why if end is None else ''
    values=frozen.aggregate(result)
    rr=np.asarray(result['rr']);qt=values.get('qt');qrs=values.get('qrs_duration')
    if qt is not None and qrs is not None and qrs<120 and len(rr)>=4 and .6<=np.median(rr)<=1.5 and np.std(rr)/np.mean(rr)<=.1:
        values['qtc_f']=float(qt/np.cbrt(np.median(rr)))
    result.update(method=method,metrics=values,reason='' if 'qt' in values else 'window_quality_or_dispersion')
    return result
