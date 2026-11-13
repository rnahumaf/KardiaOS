import copy,io,json,os
os.environ['QT_QPA_PLATFORM']='offscreen'
import numpy as np
import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication,QCheckBox
from PySide6.QtCore import QSettings
from kardiaos.processing import EMPIRICAL,REFERENCED,DEFAULT_FILTERS,set_profile,profile_info,snapshot
from kardiaos.orientation import evidence_state
from kardiaos.automatic_analysis import automatic_analysis,analysis_key,cache_analysis
from kardiaos.recording import save_recording,load_recording
from kardiaos.report import pdf_bytes
from kardiaos.preview import PrintPreview
from kardiaos.app import Window
from test_measurements import signal_record
from test_automatic_analysis import fake_infer
from test_analysis_dialog import wait


def operational():
    r=signal_record();r.meta['synthetic']=False;set_profile(r,EMPIRICAL);r.configure(DEFAULT_FILTERS);return r


def test_assumed_profile_never_validates_evidence_and_uses_display_input(tmp_path):
    r=operational();before=r.raw[:r.n].copy();meta=copy.deepcopy(r.meta);calls={}
    def infer(key,x,cancel):calls[key]=x.copy();return fake_infer(key,x,cancel)
    a=automatic_analysis(r,infer=infer,duration=10)
    assert len(a['scenarios'])==3 and all(v['raw_multipliers'] in [(1,),(1,1)] for v in a['scenarios'])
    assert a['operational_profile']['status']=='assumed_empirical'
    assert r.meta==meta and not r.meta['amplitude_verified']
    assert evidence_state(r)['decoder']=={'I':None,'II':None}
    i,j=a['scenarios'][0]['first_sample'],a['scenarios'][0]['last_sample_exclusive']
    np.testing.assert_allclose(calls['ecgfounder_1l'],r.lead_values(i,j)[:,:1].T)
    np.testing.assert_allclose(calls['deeppsp_6l'],r.lead_values(i,j).T)
    np.testing.assert_allclose(calls['deeppsp_6l'][2],calls['deeppsp_6l'][1]-calls['deeppsp_6l'][0])
    path=tmp_path/'synthetic-profile.kardia';save_recording(path,r);loaded=load_recording(path)
    assert profile_info(loaded)==profile_info(r) and not loaded.meta['amplitude_verified']
    np.testing.assert_array_equal(before,loaded.raw[:loaded.n])


def test_legacy_stays_reference_gated_until_profile_selected():
    r=signal_record();r.meta['synthetic']=False
    assert not automatic_analysis(r,infer=fake_infer)['scenarios']
    set_profile(r,EMPIRICAL);assert len(automatic_analysis(r,infer=fake_infer)['scenarios'])==3
    set_profile(r,REFERENCED);assert not automatic_analysis(r,infer=fake_infer)['scenarios']


def test_profile_scopes_quality_and_cache_invalidation():
    r=operational();a=automatic_analysis(r,infer=fake_infer,offset=10,duration=10)
    assert all(v['offset_seconds']==10 for v in a['scenarios'])
    assert a['measurements']['offset_seconds']>=10
    assert a['measurements']['offset_seconds']+a['measurements']['duration_seconds']<=20+1e-6
    key=analysis_key(r,offset=10,duration=10);assert key!=analysis_key(r,offset=0,duration=10)
    r.configure(type(DEFAULT_FILTERS)(.05,40,60));assert key!=analysis_key(r,offset=10,duration=10)
    r.quality[300:600]=False
    assert not automatic_analysis(r,infer=fake_infer,duration=10)['scenarios']
    assert len(automatic_analysis(r,infer=fake_infer,offset=10,duration=10)['scenarios'])==3


def test_results_of_other_signal_rejected_and_other_window_not_printed():
    r=operational();a=automatic_analysis(r,infer=fake_infer,duration=10)
    text=PdfReader(io.BytesIO(pdf_bytes(r,offset=15,analysis=a))).pages[0].extract_text()
    assert '0.2500' not in text and 'Reavaliar a janela' in text
    r.raw[1000,0]+=4
    with pytest.raises(ValueError,match='outra captura'):pdf_bytes(r,analysis=a)


def test_snapshot_cannot_race_original_edits():
    r=operational();job=snapshot(r);before=job.raw.copy();r.raw[1000,0]+=4;r.meta['mv_per_count']*=2
    np.testing.assert_array_equal(job.raw,before);assert job.meta['mv_per_count']!=r.meta['mv_per_count']
    with pytest.raises(ValueError):job.raw[1,0]=4


def test_preferences_roundtrip_keeps_unrelated_keys(tmp_path):
    app=QApplication.instance() or QApplication([]);settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat)
    settings.setValue('screens/test/x',4.2);settings.setValue('amplitude/factor',.0002)
    w=Window(settings=settings);w.tick_timer.stop();w.gain.setCurrentIndex(0);w.notch.setCurrentIndex(0);w.autorun.setChecked(False);w.duration.setValue(60);w.save_preferences();w.close()
    v=Window(settings=settings);v.tick_timer.stop()
    assert v.gain.currentData()==5 and v.notch.currentData()==0 and not v.autorun.isChecked() and v.duration.value()==60
    assert float(settings.value('screens/test/x'))==4.2 and float(settings.value('amplitude/factor'))==.0002
    assert v.profile_combo.currentData()==EMPIRICAL;v.close()


def test_preview_offset_change_cancels_old_job_and_keeps_exact_window(monkeypatch):
    import time
    from kardiaos.automatic_analysis import Cancelled
    app=QApplication.instance() or QApplication([])
    def delayed(key,x,cancel):
        for _ in range(5):
            if cancel():raise Cancelled()
            time.sleep(.01)
        return fake_infer(key,x,cancel)
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel,**kw:automatic_analysis(r,emit,cancel,delayed,**kw))
    r=operational();p=PrintPreview(r);p.offset.setValue(10)
    wait(app,lambda:p.analysis['status']=='completed' and not p.thread.isRunning(),seconds=15)
    assert p.analysis['scope']['offset_seconds']==10
    assert all(v['offset_seconds']==10 for v in p.analysis['scenarios'])
    text=PdfReader(io.BytesIO(p.data)).pages[0].extract_text();assert '10-20 s' in text
    assert p.save_button.isEnabled();p.close()


def test_raw_preview_never_attaches_filtered_scores():
    app=QApplication.instance() or QApplication([]);r=operational();a=automatic_analysis(r,infer=fake_infer,duration=10);cache_analysis(r,a)
    p=PrintPreview(r,raw=True,autostart=False)
    text=PdfReader(io.BytesIO(p.data)).pages[0].extract_text();assert '0.2500' not in text;p.close()


def test_profile_timing_invariance_and_delineator_boundary_abstention():
    from kardiaos.measurements import measure_recording
    results=[]
    for invert,gain in [(False,1),(True,.5)]:
        r=signal_record(invert=invert,gain=gain);set_profile(r,EMPIRICAL);r.configure(DEFAULT_FILTERS)
        results.append(measure_recording(r))
    assert results[0]['metrics']['heart_rate']['value']==pytest.approx(60,abs=.5)
    # A causal baseline filter can merge the QRS tail with the next wave.
    # Abstention is required for this fixture; the algorithm must not complete it.
    assert results[0]['metrics']['qrs_duration']['value'] is None
    assert 'borda/onda adjacente' in results[0]['metrics']['qrs_duration']['reason']
    known=signal_record();set_profile(known,EMPIRICAL);known.configure(type(DEFAULT_FILTERS)(0,0,0))
    measured=measure_recording(known)
    assert measured['metrics']['qrs_duration']['value']==pytest.approx(80,abs=20)
    assert measured['metrics']['qt']['value']==pytest.approx(400,abs=45)
    for key in results[0]['metrics']:
        a,b=results[0]['metrics'][key]['value'],results[1]['metrics'][key]['value']
        if a is None:assert b is None
        else:assert b==pytest.approx(a,abs=5)
    narrow=signal_record(qrs_width=.04);set_profile(narrow,EMPIRICAL);narrow.configure(DEFAULT_FILTERS)
    assert measure_recording(narrow)['metrics']['qtc_f']['value'] is None


@pytest.mark.parametrize('problem',['short','noise','gap','missing_waves'])
def test_operational_profile_abstains_on_unsupported_measurements(problem):
    from kardiaos.measurements import measure_recording
    r=signal_record(seconds=8 if problem=='short' else 31,noise=.7 if problem=='noise' else 0,p=problem!='missing_waves',t=problem!='missing_waves')
    if problem=='gap':r.quality[::1500]=False
    set_profile(r,EMPIRICAL);r.configure(DEFAULT_FILTERS);result=measure_recording(r)
    if problem!='missing_waves':assert all(m['value'] is None and m['reason'] for m in result['metrics'].values())
    else:assert result['metrics']['p_duration']['value'] is None and result['metrics']['qt']['value'] is None


def test_automatic_selection_stays_inside_printed_di_interval():
    r=operational();r.quality[300:1800]=False
    a=automatic_analysis(r,infer=fake_infer,duration=30)
    assert len(a['scenarios'])==3
    assert all(5<=v['offset_seconds']<=20 for v in a['scenarios'])
    assert not automatic_analysis(r,infer=fake_infer,duration=10)['scenarios']
    text=PdfReader(io.BytesIO(pdf_bytes(r,layout='di',analysis=a))).pages[0].extract_text()
    assert '0.2500' in text and 'I+' not in text


def test_main_background_processing_repeats_after_filter_change(monkeypatch,tmp_path):
    import time
    app=QApplication.instance() or QApplication([])
    def delayed(key,x,cancel):
        time.sleep(.02);return fake_infer(key,x,cancel)
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel,**kw:automatic_analysis(r,emit,cancel,delayed,**kw))
    settings=QSettings(str(tmp_path/'background.ini'),QSettings.Format.IniFormat)
    w=Window(settings=settings);w.tick_timer.stop();w.recording=operational();w.paper.recording=w.recording
    w.start_background_analysis();w.apply_filters(type(DEFAULT_FILTERS)(.05,40,60));w._analysis_timer.stop();w.start_background_analysis()
    wait(app,lambda:getattr(w.recording,'_automatic_analysis',None) is not None and not w._analysis_thread.isRunning(),seconds=15)
    result=w.recording._automatic_analysis
    assert result['source_key']==analysis_key(w.recording)
    assert result['operational_profile']['filters']['baseline']==.05
    assert len(result['scenarios'])==3
    w.autorun.setChecked(False);w.dirty=False;w.close()


def test_six_lead_vertical_origin_changes_without_compressing_scale():
    from kardiaos.report import page_plan
    from reportlab.lib.units import mm
    from pypdf.generic import ContentStream
    r=operational();a=automatic_analysis(r,infer=fake_infer,duration=10)
    plan=page_plan(r,analysis=a);assert len(plan['rows'])==7
    for row in plan['rows']:
        y=row['baseline']+plan['values'][row['first']:row['last'],row['lead']]*10
        assert np.nanmin(y)>=row['top']-row['h']+1 and np.nanmax(y)<=row['top']-6
    reader=PdfReader(io.BytesIO(pdf_bytes(r,analysis=a)))
    ops=ContentStream(reader.pages[0].get_contents(),reader).operations
    # Calibration pulse is 1 mV at 10 mm/mV and 200 ms at 25 mm/s.
    pulse=[]
    for i,(args,op) in enumerate(ops):
        if op==b'm' and len(args)==2 and abs(float(args[0])-11*mm)<1e-3:
            pts=[args]+[v for v,code in ops[i+1:i+6] if code==b'l']
            if len(pts)==6:pulse=pts;break
    assert pulse
    assert float(pulse[2][1])-float(pulse[1][1])==pytest.approx(10*mm,abs=.001)
    assert float(pulse[3][0])-float(pulse[2][0])==pytest.approx(5*mm,abs=.001)



def test_cancelled_close_preserves_session_and_allows_new_analysis(monkeypatch,tmp_path):
    import time
    app=QApplication.instance() or QApplication([])
    def delayed(key,x,cancel):
        time.sleep(.03);return fake_infer(key,x,cancel)
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel,**kw:automatic_analysis(r,emit,cancel,delayed,**kw))
    settings=QSettings(str(tmp_path/'close.ini'),QSettings.Format.IniFormat)
    w=Window(settings=settings);w.tick_timer.stop();w.recording=operational();w.paper.recording=w.recording;w.dirty=True
    monkeypatch.setattr(w,'protect_recording',lambda:False)
    w.show();app.processEvents();w.start_background_analysis();w.close()
    wait(app,lambda:not w._analysis_thread.isRunning() and not w._closing_analysis)
    assert w.isVisible() and w.dirty and w.recording.n>0
    w.start_background_analysis()
    wait(app,lambda:not w._analysis_thread.isRunning() and getattr(w.recording,'_automatic_analysis',None) is not None)
    monkeypatch.setattr(w,'protect_recording',lambda:True);w.dirty=False;w.close()



def test_model_window_after_gap_never_spills_outside_requested_interval():
    r=operational();r.times[1800:r.n]+=.11;r.meta['end']=r.last_time
    # The requested start lies inside a gap; a complete model window would end
    # 110 ms beyond a ten-second print interval. Never relabel it as the request.
    blocked=automatic_analysis(r,infer=fake_infer,offset=5,duration=10)
    assert not blocked['scenarios'] and blocked['unavailable']
    allowed=automatic_analysis(r,infer=fake_infer,offset=5,duration=11)
    assert len(allowed['scenarios'])==3
    for item in allowed['scenarios']:
        actual=float(r.times[item['first_sample']]-r.meta['start'])
        assert item['offset_seconds']==pytest.approx(actual)
        assert actual==pytest.approx(5.11) and actual+10<=16
