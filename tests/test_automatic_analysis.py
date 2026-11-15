import numpy as np
from kardiaos.automatic_analysis import automatic_analysis,first_window,Cancelled
from kardiaos.research import catalog,analyze
from test_measurements import signal_record


def fake_infer(key,values,cancelled):
    if cancelled(): raise Cancelled()
    return dict(scores=[dict(v,score=.25) for v in catalog()['models'][key]['labels']],
                checkpoint_sha256=catalog()['models'][key]['sha256'],preprocessing='test double',runtime='test double')


def test_all_unknown_orientations_preserved_without_calibrating_or_mutating():
    r=signal_record();r.meta['synthetic']=False
    before=r.raw[:r.n].copy();calls=[]
    def infer(key,values,cancel):calls.append((key,values.copy()));return fake_infer(key,values,cancel)
    result=automatic_analysis(r,infer=infer,include_models=True,technical_mode=True)
    assert len(result['scenarios'])==10
    assert {v['hypothesis'] for v in result['scenarios'] if v['model']=='deeppsp_6l'}=={'I+ II+','I+ II-','I- II+','I- II-'}
    for key,x in calls:
        if key=='deeppsp_6l':np.testing.assert_allclose(x[2],x[1]-x[0],atol=1e-12)
    np.testing.assert_array_equal(before,r.raw[:r.n])
    assert r.meta['amplitude_verified'] is False and 'research_calibration' not in r.meta
    assert analyze(r,'ecgfounder_1l')['status']=='inconclusive'


def test_single_lead_never_fills_missing_channels():
    r=signal_record();r.raw[:r.n,1]|=1;r.lead_modes[:r.n]=1
    result=automatic_analysis(r,infer=fake_infer,include_models=True)
    assert len(result['scenarios'])==1
    assert all(v['model']=='ecgfounder_1l' for v in result['scenarios'])
    assert len(result['unavailable'])==2


def test_noise_and_absence_never_call_models():
    def forbidden(*args):raise AssertionError('Must not infer')
    for r in (None,signal_record(noise=.7)):
        result=automatic_analysis(r,infer=forbidden)
        assert not result['scenarios'] and len(result['unavailable'])==3


def test_cancellation_between_scenarios_and_repeat_has_no_stale_rows():
    emitted=[]
    result=automatic_analysis(signal_record(),lambda v:emitted.append(v),lambda:any(v['kind']=='scenario' for v in emitted),fake_infer,include_models=True)
    assert result['status']=='cancelled' and len(result['scenarios'])==1
    again=automatic_analysis(signal_record(),infer=fake_infer,include_models=True)
    assert again['status']=='completed' and len(again['scenarios'])==3


def test_first_technical_window_not_selected_by_model_score():
    r=signal_record();r.quality[300:600]=False
    check,reason=first_window(r,'ecgfounder_1l')
    assert reason is None and check['offset_seconds']==1


def test_worker_cancellation_terminates_only_own_background_process(monkeypatch):
    import subprocess,sys,time,pytest
    import kardiaos.automatic_analysis as module
    original=subprocess.Popen;processes=[]
    def child(args,**kwargs):
        process=original([sys.executable,'-I','-c','import time; time.sleep(20)'],**kwargs)
        processes.append(process);return process
    monkeypatch.setattr(module,'runtime_config',lambda:dict(python=sys.executable,models_dir='.'))
    monkeypatch.setattr(module.subprocess,'Popen',child)
    began=time.monotonic()
    with pytest.raises(Cancelled):module.worker_scores('ecgfounder_1l',np.ones((1,3000)),lambda:time.monotonic()-began>.3)
    assert len(processes)==1 and processes[0].poll() is not None
