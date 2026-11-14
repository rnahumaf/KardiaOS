import copy
import numpy as np
import pytest
from kardiaos.measurements import measure_recording,descriptions,QUALIFICATION
from kardiaos.measurement_engine import measure_recording as candidate_measure
from kardiaos.delineation import delineate,aggregate,preprocess
from kardiaos.signal import FilterConfig
from kardiaos.processing import set_profile,EMPIRICAL
from test_measurements import signal_record

def wave(t,center,width,amplitude):
    z=(t-center)/(width/2)
    return np.where(abs(z)<1,amplitude*.5*(1+np.cos(np.pi*np.clip(z,-1,1))),0)

def stress_signal(kind):
    t=np.arange(9000)/300;x=np.zeros(9000)
    for b in np.arange(.8,29,1):
        x+=wave(t,b,.16 if kind=='wide' else .08,1)
        if kind=='notched':x+=wave(t,b-.055,.05,-.25)+wave(t,b+.06,.05,-.35)
        if kind not in ('absent','low_p'):x+=wave(t,b-.2,.1,-.18 if kind=='negative_p' else .18)
        if kind=='low_p':x+=wave(t,b-.2,.1,.005)
        if kind=='biphasic_p':x+=wave(t,b-.145,.1,-.18)
        if kind not in ('absent','low_t'):x+=wave(t,b+.28,.16,-.3 if kind=='negative_t' else .3)
        if kind=='low_t':x+=wave(t,b+.28,.16,.005)
        if kind=='biphasic_t':x+=wave(t,b+.38,.16,-.3)
    if kind=='drift':x+=.5*np.sin(2*np.pi*.2*t)
    if kind=='noise':x+=np.random.default_rng(42).normal(0,.7,len(t))
    return x

@pytest.mark.parametrize('kind',['clean','wide','notched','negative_p','negative_t','drift','biphasic_p','biphasic_t','low_p','low_t','absent','noise'])
def test_known_shapes_gain_sign_and_abstention(kind):
    x=stress_signal(kind);a=aggregate(delineate(x));b=aggregate(delineate(-x*3))
    assert a.keys()==b.keys()
    for key in a:assert b[key]==pytest.approx(a[key],abs=3.34)
    if kind=='noise':assert not a;return
    assert a['heart_rate']==pytest.approx(60,abs=.5)
    truth={'wide':160,'notched':165}.get(kind,80)
    assert a['qrs_duration']==pytest.approx(truth,abs=20.01)
    if kind in ('biphasic_p','low_p','absent'):assert 'p_duration' not in a
    elif kind!='biphasic_t':assert a['p_duration']==pytest.approx(100,abs=20)
    if kind in ('biphasic_t','low_t','absent'):assert 'qt' not in a

def test_release_policy_withholds_qt_qtc_even_for_perfect_synthetic_input():
    r=signal_record();a=measure_recording(r);candidate=candidate_measure(r)
    assert candidate['metrics']['qt']['value']==pytest.approx(400,abs=35)
    for v in [a]+a['additional_leads']:
        for key in ('qt','qtc_f'):
            assert v['metrics'][key]['value'] is None
            assert v['metrics'][key]['unavailable_scope']=='method_qualification'
            assert '50%' in v['metrics'][key]['reason']
        assert all('toff' not in p and 'ton' not in p for p in v['fiducials'])
    assert QUALIFICATION['I']['qt_coverage']<.5 and QUALIFICATION['II']['qt_coverage']<.5

def test_measurement_filter_independent_of_display_and_raw_evidence_preserved():
    r=signal_record();set_profile(r,EMPIRICAL);before=r.raw[:r.n].copy();meta=copy.deepcopy(r.meta)
    results=[]
    for config in [FilterConfig(.5,40,60),FilterConfig(1,25,0),FilterConfig(.05,80,50)]:
        r.configure(config);results.append(measure_recording(r))
    for key in ('heart_rate','p_duration','qrs_duration'):
        assert len({v['metrics'][key]['value'] for v in results})==1
    assert results[0]['pipeline']['source']=='raw' and not results[0]['pipeline']['display_pipeline']
    np.testing.assert_array_equal(before,r.raw[:r.n])
    assert r.meta['amplitude_verified']==meta['amplitude_verified']==False
    assert r.meta.get('orientation_evidence')==meta.get('orientation_evidence')

def test_independent_leads_and_contact_settling_are_not_filled_in():
    r=signal_record();r.raw[:r.n,1]=np.random.default_rng(4).integers(-10000,10000,r.n,dtype=np.int16)&-4
    a=measure_recording(r)
    assert a['metrics']['heart_rate']['value'] is not None
    assert a['additional_leads'][0]['lead']=='II'
    assert all(m['value'] is None for m in a['additional_leads'][0]['metrics'].values())
    r.lead_modes[:r.n]=1
    assert measure_recording(r)['additional_leads']==[]
    assert measure_recording(r,lead='II')['metrics']['heart_rate']['value'] is None
    with pytest.raises(ValueError):measure_recording(r,lead='V1')

def test_candidate_qtc_rejects_irregular_rr_and_wide_qrs_independently_of_release_policy():
    for r in [signal_record(irregular=True),signal_record(qrs_width=.16)]:
        m=candidate_measure(r)
        assert m['metrics']['heart_rate']['value'] is not None
        assert m['metrics']['qrs_duration']['value'] is not None
        assert m['metrics']['qtc_f']['value'] is None
        assert 'QTc não aplicado' in m['metrics']['qtc_f']['reason']

def test_one_sample_shift_has_documented_two_endpoint_quantization_sensitivity():
    a=stress_signal('clean');b=np.roll(a,1)
    ra=delineate(a);rb=delineate(b)
    ma,mb=aggregate(ra),aggregate(rb)
    # Two independently quantized endpoints can change duration by two samples.
    # This is an observed numerical sensitivity, not a confidence interval or accuracy claim.
    for k in ma:assert mb[k]==pytest.approx(ma[k],abs=2*1000/300+.01)
    assert abs((rb['beats'][3]['qon']-ra['beats'][3]['qon'])-1)<=1

def test_deterministic_width_is_not_bundle_branch_or_st_diagnosis():
    a=measure_recording(signal_record(qrs_width=.16))
    items={v['id']:v for v in a['descriptions']}
    assert 'ms (estimativa por derivação)' in items['qrs_width']['text']
    assert '120 ms' in items['qrs_width']['criterion'] and 'Não foi validada classificação' in items['qrs_width']['criterion']
    assert items['bundle_branch']['status']=='unavailable' and 'V1/V2/V5/V6' in items['bundle_branch']['reason']
    assert items['st']['status']=='unavailable'
    a['metrics']['qrs_duration'].update(value=123,iqr_ms=[119,127])
    assert '123 ms' in descriptions(a)[0]['text']
    assert 'classificação' in descriptions(a)[0]['criterion']
