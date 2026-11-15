"""Known synthetic landmarks exercise sensitivity independently of accuracy."""
from copy import deepcopy
import numpy as np
import pytest
from kardiaos.measurement_quality import assess,attach_metrics,INTERVALS,LIMIT_SAMPLES
from kardiaos.rule_analysis import classify,features
from kardiaos.automatic_analysis import automatic_analysis
from test_measurements import signal_record
from test_rule_analysis import case,status


def known(monkeypatch,n=20,shift=None,missing=None,contrast=30):
    r,m,reps=case();points={k:v for k,v in m['global_fiducials'].items() if k!='r'}
    x=np.asarray(reps['I']['values_mv']);stacks={k:np.tile(x,(n,1))[:,:,None] for k in ('qrs','pt')}
    sources={k:dict(supporting_leads=['I'],quality={'I':contrast}) for k in points}
    calls=[]
    def delineate(*args):
        p=dict(points)
        if not calls and shift:
            key,amount=shift;p[key]+=amount
        if not calls and missing:p.pop(missing)
        calls.append(1);return p,{},{}
    monkeypatch.setattr('kardiaos.measurement_quality.delineate_medians',delineate)
    q=assess(stacks,['I'],105,1.,points,sources,1.)
    m['metrics']['qt']=dict(value=400,name='QT',unit='ms')
    attach_metrics(m,q)
    return r,m,reps,q


def test_stable_values_no_generic_warning_and_deterministic():
    r=signal_record(noise=.025);before=r.raw[:r.n].copy()
    a=automatic_analysis(r);b=automatic_analysis(r)
    assert a['measurements']['technical_quality']==b['measurements']['technical_quality']
    for key in INTERVALS:
        m=a['measurements']['metrics'][key]
        assert m['value'] is not None and m['status']=='estimated'
        assert m['quality']['status']=='stable' and not m['quality']['reason']
    assert 'baixa confiança' not in a['qtc_label']
    np.testing.assert_array_equal(r.raw[:r.n],before)


@pytest.mark.parametrize('key',list(LIMIT_SAMPLES))
def test_boundary_limit_and_one_sample_over(monkeypatch,key):
    _,_,_,q=known(monkeypatch,shift=(key,LIMIT_SAMPLES[key]));assert q['boundaries'][key]['status']=='stable'
    _,_,_,q=known(monkeypatch,shift=(key,LIMIT_SAMPLES[key]+1));assert q['boundaries'][key]['status']=='review'


def test_t_offset_fragility_does_not_change_p_qrs_pr(monkeypatch):
    r,m,reps,q=known(monkeypatch,shift=('toff',20))
    assert m['metrics']['qt']['quality']['status']=='review'
    for key in ('p_duration','qrs_duration','pr'):assert m['metrics'][key]['quality']['status']=='stable'


def test_missing_boundary_and_low_contrast_have_specific_reasons(monkeypatch):
    _,m,_,q=known(monkeypatch,missing='toff')
    assert q['boundaries']['toff']['detected_subsets']==3 and 'não reproduzido' in m['metrics']['qt']['quality']['reason']
    _,_,_,q=known(monkeypatch,contrast=11)
    assert 'baixo contraste' in q['boundaries']['pon']['reason']


def test_few_beats_preserve_values_and_suspend_dependent_rules(monkeypatch):
    r,m,reps,q=known(monkeypatch,n=9)
    assert not q['replicates'] and m['metrics']['p_duration']['value']==80
    assert m['metrics']['p_duration']['quality']['status']=='unverified'
    c=classify(r,m,reps)
    assert status(c,'irregular')=='not_detected' and status(c,'brady')=='not_detected'
    assert status(c,'qrs_wide')=='unavailable'
    assert next(v for v in c['rules'] if v['id']=='qrs_wide')['technical_status']=='indeterminate'


def coherent_quality(m,reps):
    # All replicas match the central fixture; a test changes one independent rule input.
    return dict(boundaries={k:dict(status='stable',contrast=30,detected_subsets=4) for k in ('pon','poff','qon','qoff','ton','toff')},
        replicates=[dict(values={k:v['value'] for k,v in m['metrics'].items()},features=features(m,reps)) for _ in range(4)])


def test_threshold_crossing_suspends_only_affected_rule():
    r,m,reps=case();m['metrics']['pr']['value']=199;m['technical_quality']=coherent_quality(m,reps)
    m['technical_quality']['replicates'][0]['values']['pr']=201
    c=classify(r,m,reps)
    assert status(c,'pr_long')=='unavailable' and status(c,'pr_short')=='not_detected'
    assert status(c,'qrs_wide')=='not_detected' and status(c,'qt_long')=='not_detected'


def test_amplitude_rule_uses_subset_median_features():
    r,m,reps=case();m['technical_quality']=coherent_quality(m,reps)
    for lead in ('I','aVL'):m['technical_quality']['replicates'][0]['features'][lead]['j_mv']=.15
    c=classify(r,m,reps)
    assert status(c,'j_elevation')=='unavailable' and status(c,'p_wide')=='not_detected'


def test_cancel_checked_between_subsets(monkeypatch):
    from kardiaos.automatic_analysis import Cancelled
    with pytest.raises(Cancelled):assess({'qrs':np.zeros((20,286,1))},['I'],105,1.,{},{},1.,lambda:True)
