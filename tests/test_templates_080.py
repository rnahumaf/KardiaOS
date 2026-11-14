import copy
import numpy as np
import pytest
from kardiaos.qt_templates import build,combine,label
from kardiaos.review_window import select_lead,select_window
from qt_synthetics import make,CASES

@pytest.mark.parametrize('case',CASES)
def test_raw_samples_only_integer_translated(case):
    raw,_=make(case);original=raw.copy();result=build(raw)
    np.testing.assert_array_equal(raw,original)
    for g in result['groups']:
        pre=g['r_index'];width=len(g['raw_median']);expected=np.stack([raw[p-pre:p-pre+width] for p in g['centers']])
        np.testing.assert_array_equal(g['raw_beats'],expected);np.testing.assert_array_equal(g['raw_median'],np.median(expected,axis=0))
        assert all(isinstance(s,(int,np.integer)) and abs(s)<=9 for s in g['shift_samples'])

def test_sign_gain_preserved_and_ectopic_excluded():
    x,_=make('clean');a=build(x)['groups'][0]
    np.testing.assert_allclose(build(x*.7)['groups'][0]['raw_median'],a['raw_median']*.7,atol=1e-9)
    np.testing.assert_allclose(build(-x)['groups'][0]['raw_median'],-a['raw_median'],atol=1e-9)
    ectopic=build(make('ectopic_QRS')[0]);assert all(abs(p/300-3.6)>.1 for p in ectopic['groups'][0]['original_r'])
    assert ectopic['discarded_from_dominant']>=1

def test_numeric_label_requires_technical_estimate_and_named_formula():
    r=dict(qtc_f=440.1,technical_estimate=True,formula_name='Fridericia')
    assert label('II',r)=='QTc: 440 ms (DII; Fridericia; baixa confiança)'
    for bad in (None,{},dict(qtc_f=440),dict(r,formula_name='Bazett'),dict(r,qtc_f=float('nan'))):assert label('I',bad)=='QTc: erro na estimativa'
    assert combine(build(make('clean')[0])['groups'][0],dict(metrics={},beats=[]))['qtc_f'] is None

@pytest.mark.parametrize('case',['absent_T','low_T','T_alternans','RR_dependent_T','clipped_gap'])
def test_bad_wave_cannot_be_rescued_by_a_plausible_model(case):
    raw,_=make(case);groups=build(raw)['groups']
    for g in groups:
        beats=[dict(r=p,qon=p-12,toff=p+120) for p in g['original_r']]
        assert combine(g,dict(metrics={'qt':440},beats=beats))['qtc_f'] is None

def test_t_aware_selector_never_uses_qtc_or_availability():
    entries={name:dict(quality={'eligible':True,'score':score},template={'eligible_beats':7,'groups':[dict(n_beats=7,reasons=reasons)]},result={'qtc_f':value}) for name,score,reasons,value in [('I',.99,['possible_T_alternation'],440),('II',.90,[],None)]}
    assert select_lead(entries)[0]=='II';entries['I']['result']['qtc_f']=100;entries['II']['result']['qtc_f']=900
    assert select_lead(entries)[0]=='II'

def test_five_similar_beats_required():
    raw,_=make('clean');raw[1500:]=np.random.default_rng(80).normal(0,.01,1500)
    assert not any(g['technical_eligible'] for g in build(raw)['groups'])
