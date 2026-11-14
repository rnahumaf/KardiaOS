import copy
import numpy as np
import pytest
from PySide6.QtCore import QSettings
from kardiaos.paper import trace_path
from kardiaos.app import Window
from kardiaos.qt_templates import build,combine,VISUAL_FLAGS
from kardiaos.review_window import template_supported
from kardiaos.timing_markers import p_intervals
from kardiaos.report import measurement_line
from test_review_flow_080 import record
from qt_synthetics import make

def test_trace_vectorization_preserves_every_coordinate_and_gap():
    t=np.array([0,1/300,2/300,.1,.1+1/300,.1+2/300]);v=np.array([0,1,np.nan,2,3,4.])
    path=trace_path(t,v,0,10,100,100,40)
    vertices=[path.elementAt(i) for i in range(path.elementCount())]
    assert len(vertices)==5
    np.testing.assert_allclose([(p.x,p.y) for p in vertices],[(10+tt*100,100-vv*40) for tt,vv in zip(t,v) if np.isfinite(vv)])
    assert [p.isMoveTo() for p in vertices]==[True,False,True,False,False]

@pytest.mark.parametrize('milliseconds,millimeters',[(80,2),(120,3),(126.6666667,3.166666667)])
def test_time_axis_has_exact_25_mm_per_second(milliseconds,millimeters):
    p=trace_path(np.array([0,milliseconds/1000]),np.array([0.,1.]),0,0,0,25,10)
    # Nonuniform points are breaks, but their physical x coordinates are unchanged.
    assert p.currentPosition().x()==pytest.approx(millimeters)

def fake_analysis():
    metric=dict(value=120,unit='ms');return dict(status='completed',selected_lead='II',report_window=dict(first_sample=0,last_sample_exclusive=3000),
        measurements=dict(lead='I',metrics=dict(p_duration=dict(value=None),heart_rate=dict(value=60,unit='bpm'),qrs_duration=dict(value=80,unit='ms')),
        additional_leads=[dict(lead='II',method_version='timing-dsp-1',metrics=dict(p_duration=metric,heart_rate=dict(value=60,unit='bpm'),qrs_duration=dict(value=80,unit='ms')),
            fiducials=[dict(r=600,pon=530,poff=566),dict(r=900,pon=830,poff=866)])]))

def test_p_markers_belong_to_measured_lead_window_and_real_endpoints():
    a=fake_analysis();points=p_intervals(a,'II',0,3000)
    assert [(v['on'],v['off'],v['duration_ms']) for v in points]==[(530,566,120),(830,866,120)]
    assert not p_intervals(a,'I',0,3000)
    assert len(p_intervals(a,'II',700,1000))==1
    assert not p_intervals(a,'II',540,1000-200)
    assert 'P: 120 ms (DII)' in measurement_line(a)
    for key,value in [('status','cancelled'),('trace_only',True)]:
        b=copy.deepcopy(a);b[key]=value;assert not p_intervals(b,'II',0,3000)
    a['measurements']['additional_leads'][0]['metrics']['p_duration']['value']=None
    assert not p_intervals(a,'II',0,3000)

def test_visual_template_is_separate_from_qt_endpoint_qualification():
    g=build(make('merged_U')[0])['groups'][0]
    assert not g['technical_eligible'] and g['visual_eligible']
    assert template_supported(dict(quality={'eligible':True},template={'groups':[g]}))
    model=dict(metrics={'qt':400},beats=[dict(r=r,qon=r-12,toff=r+108) for r in g['original_r']])
    assert combine(g,model)['qtc_f'] is None

@pytest.mark.parametrize('case',['T_alternans','RR_dependent_T','clipped_gap'])
def test_template_does_not_blur_inconsistent_morphology(case):
    out=build(make(case)[0])
    assert not any(g['visual_eligible'] for g in out['groups'])
    for g in out['groups']:assert bool(g['visual_reasons'])==bool(VISUAL_FLAGS.intersection(g['reasons']))

def test_group_audit_does_not_change_translation_or_include_ectopic():
    x,_=make('ectopic_QRS');result=build(x);g=result['groups'][0]
    assert result['grouping_limits']['minimum_correlation']==.95
    assert len(result['assignments'])==result['eligible_beats']
    assert all(abs(r/300-3.6)>.1 for r in g['original_r'])
    pre=g['r_index'];n=len(g['raw_median'])
    np.testing.assert_array_equal(g['raw_median'],np.median([x[p-pre:p-pre+n] for p in g['centers']],axis=0))

def test_serialized_pdf_p_ticks_preserve_actual_sample_durations():
    import io
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    from reportlab.lib.units import mm
    from kardiaos.automatic_analysis import automatic_analysis
    from kardiaos.report import pdf_bytes
    from test_automatic_analysis import fake_infer
    r=record();a=automatic_analysis(r,infer=fake_infer);expected=p_intervals(a,a['selected_lead'],0,r.n)
    assert expected
    reader=PdfReader(io.BytesIO(pdf_bytes(r,analysis=a)));stream=ContentStream(reader.pages[0]['/Contents'],reader)
    golden=False;xs=[];start=None
    for operands,operator in stream.operations:
        if operator==b'RG':golden=np.allclose([float(v) for v in operands],[140/255,110/255,57/255],atol=1e-6)
        if operator==b'm':start=[float(v) for v in operands]
        if operator==b'l' and golden:
            end=[float(v) for v in operands]
            assert start[0]==pytest.approx(end[0]) and abs(end[1]-start[1])/mm==pytest.approx(1.4,abs=1e-4)
            xs.append(start[0])
    assert len(xs)==2*len(expected)
    for index,beat in enumerate(expected):assert (xs[2*index+1]-xs[2*index])/mm/25*1000==pytest.approx(beat['duration_ms'],abs=.01)

def test_paused_tick_does_not_redraw_and_replay_uses_elapsed_time(tmp_path,monkeypatch):
    w=Window(settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat));w.tick_timer.stop();r=record();w.recording=w.paper.recording=r;w.paper.cursor=0
    def forbidden(*args,**kwargs):raise AssertionError('Analysis must not run from playback')
    monkeypatch.setattr('kardiaos.review_window.select_window',forbidden)
    monkeypatch.setattr('kardiaos.qt_client.infer_qt',forbidden)
    calls=[];monkeypatch.setattr(w.paper,'update',lambda *a:calls.append(1));w.tick();calls.clear()
    for _ in range(5):w.tick()
    assert not calls
    now=[100.];monkeypatch.setattr('kardiaos.app.time.monotonic',lambda:now[0]);w.replay();now[0]+=2.345;w.tick()
    assert w.paper.cursor==pytest.approx(2.345) and len(calls)==1
    w.replay();paused=w.paper.cursor;now[0]+=3;w.tick();assert w.paper.cursor==paused
    w.replay();now[0]+=1;w.tick();assert w.paper.cursor==pytest.approx(paused+1)
    w.scrub(1000);now[0]+=1;w.tick();assert not w.replaying and w.paper.cursor==r.last_time
    w.replay();now[0]+=.5;w.tick();assert w.paper.cursor==pytest.approx(r.meta['start']+.5)
    w.replaying=False;w.dirty=False;w.close()

def test_review_summary_identifies_window_while_retaining_full_record(tmp_path,monkeypatch):
    from kardiaos.automatic_analysis import automatic_analysis
    from test_automatic_analysis import fake_infer
    w=Window(settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat));w.tick_timer.stop()
    monkeypatch.setattr(w,'open_pending_preview',lambda:None)
    r=record();a=automatic_analysis(r,infer=fake_infer);w.recording=w.paper.recording=r;w.paper.cursor=r.last_time
    w.background_result(r,a);start=a['report_window']['offset_seconds'];end=start+10
    assert f'Trecho analisado: {start:g}–{end:g} s' in w.analysis_summary.text()
    assert w.paper.recording.n==r.n and r.n>3000 and w.paper.cursor==r.last_time
    w.dirty=False;w.close()
