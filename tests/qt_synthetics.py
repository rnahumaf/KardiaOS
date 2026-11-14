import numpy as np
FS=300

def pulse(t,center,width,amp):
    z=(t-center)/(width/2)
    return np.where(abs(z)<1,amp*np.cos(np.pi*z/2)**2,0.)

def fixture(case):
    t=np.arange(3000)/FS;x=np.zeros_like(t);refs=[]
    rr=1.0
    centers=np.arange(.6,10,rr)
    if case=='irregular':centers=np.cumsum([.6,.65,1.2,.8,1.25,.7,1.1,.65,1.3,.75])
    for r in centers:
        if r>=9.5:continue
        qwidth=.16 if case=='wide_qrs' else .08
        x+=pulse(t,r,qwidth,1.)+pulse(t,r-.2,.1,.12)
        amp=0 if case=='absent_T' else .008 if case=='low_T' else .25
        sign=-1 if case=='negative_T' else 1
        x+=pulse(t,r+.30,.2,amp*sign)
        if case=='biphasic_T':x-=pulse(t,r+.40,.14,.18)
        if case=='notched_T':x+=pulse(t,r+.38,.16,.20)
        if case=='separate_U':x+=pulse(t,r+.58,.10,.12)
        if case=='merged_U':x+=pulse(t,r+.43,.15,.18)
        refs.append(dict(r=r,qon=r-qwidth/2,toff=r+.40 if case not in ('biphasic_T','notched_T') else r+(.47 if case=='biphasic_T' else .46)))
    if case=='drift':x+=.3*np.sin(2*np.pi*.2*t)
    if case=='noise':x+=np.random.default_rng(812).normal(0,.05,len(x))
    if case=='gap':x[1000:1020]=np.nan
    if case=='flat':x[:]=0
    if case=='short':x=x[:2400]
    return x*4096,refs

CASES=['clean','negative_T','low_T','absent_T','biphasic_T','notched_T','separate_U','merged_U',
       'wide_qrs','irregular','drift','noise','gap','flat','short','T_alternans','RR_dependent_T','ectopic_QRS','translation_jitter','clipped_gap']

def make(case):
    if case in CASES[:15]:return fixture(case)
    if case=='clipped_gap':
        x,refs=fixture('clean');x[1200:1380]=0;return x,refs
    t=np.arange(3000)/300;x=np.zeros_like(t);refs=[]
    centers=np.arange(.6,9.5,1.)
    if case=='translation_jitter':centers=centers+np.array([0,.01,-.013,.02,-.01,.013,-.02,.003,.01])
    if case=='RR_dependent_T':centers=np.cumsum([.6,.85,1.15,.85,1.15,.85,1.15,.85,1.15])
    for j,r in enumerate(centers):
        width=.16 if case=='ectopic_QRS' and j==3 else .08
        amp=-1 if case=='ectopic_QRS' and j==3 else 1
        x+=pulse(t,r,width,amp)+pulse(t,r-.2,.1,.12)
        sign=(-1)**j if case=='T_alternans' else 1
        delay=.30+(.05*(-1)**j if case=='RR_dependent_T' else 0)
        x+=pulse(t,r+delay,.2,.25*sign)
        refs.append(dict(r=r,qon=r-width/2,toff=r+delay+.1))
    return x*4096,refs
