"""Completed-record review filtering, separate from causal live acquisition."""
import hashlib
import numpy as np
from scipy.signal import sosfiltfilt
from .signal import Processor,FS,six_leads

PIPELINE_VERSION='review-zero-phase-2'

def review_counts(recording):
    r=recording;raw=r.raw[:r.n];times=r.times[:r.n]
    digest=hashlib.blake2b(raw.tobytes()+times.tobytes()+r.quality[:r.n].tobytes(),digest_size=12).hexdigest()
    key=(digest,r.n,r.config)
    cached=getattr(r,'_review_cache',None)
    if cached is not None and cached[0]==key:return cached[1]
    result=raw.astype(float).copy();sos=Processor(r.config).sos
    time_breaks=~np.isclose(np.diff(times),1/FS,atol=1e-6,rtol=0)
    if len(sos):
        from .contact import channel_available
        available=channel_available(raw)&r.quality[:r.n,None]
        for channel in (0,1):
            valid=available[:,channel]
            cuts=np.r_[0,np.flatnonzero(time_breaks|(valid[1:]!=valid[:-1]))+1,r.n]
            for a,b in zip(cuts[:-1],cuts[1:]):
                # Invalid contact cannot influence a neighbouring qualified interval.
                if b>a and valid[a] and b-a>max(30,6*len(sos)+3):
                    result[a:b,channel]=sosfiltfilt(sos,result[a:b,channel])
    result.flags.writeable=False;r._review_cache=(key,result)
    return result

def completed(recording):
    return recording is not None and recording.meta.get('end') is not None

def waveform_values(recording,first,last,raw=False,mask_contact=True):
    from .processing import scale_and_signs
    from .contact import channel_available
    r=recording;factor,signs=scale_and_signs(r)
    source=r.raw if raw else review_counts(r) if completed(r) else r.filtered
    native=source[first:last].astype(float)*np.asarray(signs)
    result=six_leads(native)*factor
    modes=r.lead_modes[first:last]
    available=channel_available(r.raw[first:last])
    # A trace-only fallback may show the observed I samples with invalid contact,
    # but never invents a second lead or derived channels from unavailable data.
    if mask_contact:
        one=(modes>0)&available[:,0]&r.quality[first:last]
        result[~one,0]=np.nan
    six=(modes==6)&available.all(axis=1)
    if mask_contact:six &= r.quality[first:last]
    result[~six,1:]=np.nan
    return result
