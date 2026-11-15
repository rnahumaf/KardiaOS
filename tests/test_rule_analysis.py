"""Rule boundary tests use constructed signals and known amplitudes only."""
from copy import deepcopy
import numpy as np
import pytest
from kardiaos.rule_analysis import classify
from kardiaos.automatic_analysis import automatic_analysis, analysis_key, cache_analysis, cached_analysis
from kardiaos.recording import save_recording, load_recording
from kardiaos.global_median import analyze
from qt_synthetics import pulse
from test_measurements import signal_record


def case():
    r=signal_record();r.meta['clinical_context']=dict(age_years=40,sex='male')
    t=(np.arange(286)-105)/300
    x=pulse(t,0,.08,1)+pulse(t,-.16,.08,.15)+pulse(t,.28,.16,.25)
    points=dict(r=105,pon=45,poff=69,qon=93,qoff=117,ton=165,toff=213)
    reps={lead:dict(values_mv=x*gain,pt_values_mv=x*gain,aligned_beats_mv=np.tile(x*gain,(20,1)))
          for lead,gain in [('I',1),('II',.7),('III',-.3),('aVR',-.85),('aVL',.65),('aVF',.2)]}
    m=dict(global_fiducials=points,metrics={k:dict(value=v) for k,v in
        [('heart_rate',60),('pr',160),('qrs_duration',80),('p_duration',80),('qtc_f',400)]},
        alignment=dict(accepted_beats=20,excluded=[],unusable_segments=[],rhythm=dict(rr_seconds=[1.]*20)))
    return r,m,reps


def status(result,key):return next(v['status'] for v in result['rules'] if v['id']==key)


def test_normal_in_evaluated_criteria_retains_missing_items_and_requires_sinus():
    r,m,reps=case();c=classify(r,m,reps)
    assert c['summary']=='Sinusal, regular, normal nos critérios avaliados'
    assert c['sinus_supported'] and c['regular'] and not c['missing']
    r.meta['clinical_context'].pop('sex');c=classify(r,m,reps)
    assert c['status']=='no_findings' and status(c,'qt_long')=='not_detected' and not c['missing']
    r.meta['clinical_context']['sex']='male';m['global_fiducials'].pop('pon')
    assert classify(r,m,reps)['status']=='inconclusive'


@pytest.mark.parametrize('age',[None,10,False,-2,float('nan')])
def test_missing_age_uses_assumption_but_known_child_remains_unavailable(age):
    r,m,reps=case();r.meta['clinical_context']['age_years']=age;m['metrics']['heart_rate']['value']=45
    c=classify(r,m,reps)
    if age==10:
        assert status(c,'brady')=='unavailable' and c['missing']
    else:
        assert status(c,'brady')=='detected'
        assert any('Idade não informada' in v for row in c['rules'] for v in row['limitations'])


@pytest.mark.parametrize('key,metric,value',[('brady','heart_rate',59),('tachy','heart_rate',101),
    ('pr_short','pr',119),('pr_long','pr',201),('p_wide','p_duration',120),('qrs_wide','qrs_duration',120)])
def test_interval_rules_and_exact_thresholds(key,metric,value):
    r,m,reps=case();m['metrics'][metric]['value']=value
    assert status(classify(r,m,reps),key)=='detected'
    m['metrics'][metric]['value']=None
    assert status(classify(r,m,reps),key)=='unavailable'


def test_qtc_uses_sex_and_derived_measurement_availability():
    r,m,reps=case();m['metrics']['qtc_f']['value']=455
    assert status(classify(r,m,reps),'qt_long')=='detected'
    r.meta['clinical_context']['sex']='female'
    assert status(classify(r,m,reps),'qt_long')=='not_detected'
    m['metrics']['qtc_f']['value']=None
    assert status(classify(r,m,reps),'qt_long')=='unavailable'


def test_st_requires_contiguous_leads_and_uses_pr_baseline():
    r,m,reps=case()
    for l in ('I','aVL'):reps[l]['values_mv'][116:159]+=.15
    c=classify(r,m,reps);assert status(c,'j_elevation')=='detected'
    assert c['features']['I']['j_mv']==pytest.approx(.15,abs=.01)
    # A common DC offset must not create or remove an amplitude criterion.
    shifted=deepcopy(reps)
    for rep in shifted.values():
        for key in ('values_mv','pt_values_mv','aligned_beats_mv'):rep[key]+=4
    assert status(classify(r,m,shifted),'j_elevation')=='detected'
    reps['aVL']['values_mv'][116:159]-=.15
    assert status(classify(r,m,reps),'j_elevation')=='not_detected'


def test_st_depression_t_inversion_and_q_require_real_contiguity():
    r,m,reps=case()
    for l in ('II','aVF'):
        reps[l]['values_mv'][120:159]-=.08
        reps[l]['pt_values_mv'][165:214]=-pulse((np.arange(49)+165-105)/300,.28,.16,.2)
        reps[l]['values_mv'][93:104]=-.2
    c=classify(r,m,reps)
    for k in ('st_depression','t_inversion','q_prominent'):assert status(c,k)=='detected'
    assert c['features']['II']['q_ms']>=30
    assert all(v['amplitude_estimated'] for v in c['findings'] if v['id'] in ('st_depression','t_inversion','q_prominent'))


def test_isolated_iii_inversion_and_avr_are_not_group_findings():
    r,m,reps=case();c=classify(r,m,reps)
    assert c['features']['III']['t_mv']<0 and c['features']['aVR']['t_mv']<0
    assert status(c,'t_inversion')=='not_detected'
    reps={'I':reps['I']};c=classify(r,m,reps)
    assert c['status']=='inconclusive' and status(c,'q_prominent')=='unavailable'


def test_excluded_beat_and_irregular_rr_cannot_generate_sinus_normal_summary():
    r,m,reps=case();m['alignment']['excluded']=[dict(sample=1800)]
    c=classify(r,m,reps);assert not c['sinus_supported'] and c['status']=='inconclusive'
    m['alignment']['rhythm']['rr_seconds'][3]=1.4
    c=classify(r,m,reps);assert not c['regular'] and status(c,'irregular')=='detected'
    r.meta.pop('clinical_context')
    c=classify(r,m,reps)
    assert c['status']=='findings' and c['summary'].startswith('Achados na análise automática')
    assert status(c,'irregular')=='detected'


def test_default_path_never_invokes_models_and_preserves_raw():
    r=signal_record();before=r.raw.copy()
    def forbidden(*args):raise AssertionError('Default rules must not load any neural model')
    a=automatic_analysis(r,infer=forbidden)
    assert a['classification'] and not a['scenarios'] and not a['models_requested']
    np.testing.assert_array_equal(r.raw,before)


def test_demographics_invalidate_cache_and_survive_explicit_save(tmp_path):
    r=signal_record();a=automatic_analysis(r);cache_analysis(r,a);old=analysis_key(r)
    r.meta['clinical_context']=dict(age_years=40,sex='female')
    assert analysis_key(r)!=old and cached_analysis(r) is None
    path=tmp_path/'synthetic-context.kardia';save_recording(path,r)
    assert load_recording(path).meta['clinical_context']==r.meta['clinical_context']


def test_t_onset_changes_with_wave_timing_not_fixed_r_offset():
    a,_,_,_=analyze(signal_record(t_center=.28))
    b,_,_,_=analyze(signal_record(t_center=.35))
    delta=(b['global_fiducials']['ton']-a['global_fiducials']['ton'])/300
    assert delta==pytest.approx(.07,abs=.02)
    assert b['global_fiducials']['toff']>a['global_fiducials']['toff']

def test_manual_neural_is_explicit(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from kardiaos.analysis_dialog import AutomaticAnalysisDialog
    from test_analysis_dialog import wait
    app=QApplication.instance();r=signal_record();d=AutomaticAnalysisDialog(r,autostart=False)
    d.show();d.start();wait(app,lambda:d.result is not None and not d.busy() and d.neural_button.isEnabled())
    calls=[]
    class Manual:
        def __init__(self,record,parent):
            calls.append(record)
            class Offset:
                def setValue(self,value):pass
            self.offset=Offset()
        def exec(self):pass
    monkeypatch.setattr('kardiaos.research_dialog.ResearchDialog',Manual)
    assert not calls
    d.neural_button.click()
    assert len(calls)==1 and calls[0] is not r
    d.close()
