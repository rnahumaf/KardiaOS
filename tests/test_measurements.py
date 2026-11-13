import numpy as np
import pytest
from kardiaos.recording import Recording
from kardiaos.measurements import measure_recording


def signal_record(seconds=31, rr=1., p=True, t=True, noise=0, invert=False, gain=1, qrs_width=.08, t_center=.28, irregular=False):
    time=np.arange(int(seconds*300))/300
    x=np.zeros(len(time))
    beat_times = np.arange(.6,seconds,rr) if not irregular else .6+np.cumsum(np.tile([.7,1.3],int(seconds)))
    for beat in beat_times[beat_times<seconds]:
        for center,width,amp in [(beat,qrs_width,1.),(beat-.20,.10,.18 if p else 0),(beat+t_center,.16,.3 if t else 0)]:
            z=(time-center)/(width/2);mask=abs(z)<1
            x[mask]+=amp*.5*(1+np.cos(np.pi*z[mask]))
    x+=np.random.default_rng(42).normal(0,noise,len(x))
    raw=np.round(x*gain*(-1 if invert else 1)*5000/4)*4
    r=Recording(synthetic=True)
    r.append(0,np.column_stack([raw,raw*.6]).astype(np.int16)&-4,True)
    r.meta.update(start=1.,end=r.last_time)
    return r


def test_known_synthetic_timing_and_sign_invariance():
    a=measure_recording(signal_record());b=measure_recording(signal_record(invert=True,gain=.5))
    assert a['metrics']['heart_rate']['value']==pytest.approx(60,abs=.5)
    for key,truth,tolerance in [('p_duration',100,25),('qrs_duration',80,20),('qt',400,45),('qtc_f',400,45)]:
        assert a['metrics'][key]['value']==pytest.approx(truth,abs=tolerance),a
        assert b['metrics'][key]['value']==pytest.approx(a['metrics'][key]['value'],abs=5)
    assert a['metrics']['qtc_f']['formula']=='QTcF = QT(ms) / RR(s)^(1/3)'


@pytest.mark.parametrize('problem',['absent','short','flat','noise','clock','rate','contact'])
def test_unavailable_inputs_do_not_invent_values(problem):
    r=signal_record()
    if problem=='absent':r=None
    elif problem=='short':r.n=2000
    elif problem=='flat':r.raw[:r.n]=0
    elif problem=='noise':r=signal_record(noise=.7)
    elif problem=='clock':r.times[1000:r.n]+=np.arange(r.n-1000)*.0001
    elif problem=='rate':r.meta['sample_rate']=500
    elif problem=='contact':r.quality[:r.n]=False
    result=measure_recording(r)
    assert all(v['value'] is None and v['reason'] for v in result['metrics'].values()),result


def test_missing_waves_abstain_and_raw_is_unchanged():
    r=signal_record(p=False,t=False);before=r.raw[:r.n].copy()
    result=measure_recording(r)
    assert result['metrics']['heart_rate']['value'] is not None
    assert result['metrics']['p_duration']['value'] is None,result
    assert result['metrics']['qt']['value'] is None,result
    np.testing.assert_array_equal(before,r.raw[:r.n])


def test_gap_is_not_bridged_and_short_remaining_runs_abstain():
    r=signal_record(seconds=16)
    r.times[2400:r.n]+=.2;r.meta['end']=r.last_time
    assert measure_recording(r)['metrics']['heart_rate']['value'] is None


def test_time_measurements_do_not_mark_amplitude_or_orientation_verified():
    r=signal_record();r.meta['synthetic']=False
    result=measure_recording(r)
    assert result['metrics']['heart_rate']['value']==pytest.approx(60,abs=.5)
    assert r.meta['amplitude_verified'] is False
    assert 'research_calibration' not in r.meta
    assert 'nominais' in result['timebase']


def test_wide_qrs_does_not_receive_routine_qtc():
    result=measure_recording(signal_record(qrs_width=.16))
    assert result['metrics']['heart_rate']['value'] is not None
    assert result['metrics']['qtc_f']['value'] is None,result


def test_irregular_rr_and_t_at_window_boundary_abstain():
    for r in [signal_record(irregular=True),signal_record(t_center=.5)]:
        result=measure_recording(r)
        assert result['metrics']['qtc_f']['value'] is None,result
        assert result['metrics']['qtc_f']['reason']
