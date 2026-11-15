import copy,io
import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from kardiaos.app import Window
from kardiaos.automatic_analysis import automatic_analysis,analysis_key,cache_analysis
from kardiaos.processing import set_profile,EMPIRICAL,DEFAULT_FILTERS
from kardiaos.review_window import select_window
from kardiaos.review_signal import review_counts
from kardiaos.report import page_plan,pdf_bytes
from test_measurements import signal_record
from test_automatic_analysis import fake_infer

def record():
    r=signal_record();set_profile(r,EMPIRICAL);r.configure(DEFAULT_FILTERS);return r

def test_models_keep_report_window_but_medians_use_full_recording():
    r=record();r.quality[300:1500]=False;before=r.raw.copy();a=automatic_analysis(r,infer=fake_infer,include_models=True)
    w=a['report_window'];assert w['first_sample']>=1500 and w['last_sample_exclusive']-w['first_sample']==3000
    for item in a['scenarios']:
        assert item['first_sample']==w['first_sample'] and item['last_sample_exclusive']==w['last_sample_exclusive'] and not item['cached']
    for item in a['representative'].values():
        assert item['source_first_sample']<w['first_sample'] and item['source_last_sample_exclusive']>w['last_sample_exclusive']
    for m in [a['measurements']]+a['measurements']['additional_leads']:
        assert m['offset_seconds']==0 and m['duration_seconds']>10 and m['global_intervals']
    np.testing.assert_array_equal(before,r.raw)

def test_review_zero_phase_is_gap_segmented_and_cache_invalidates():
    from scipy.signal import sosfiltfilt
    from kardiaos.signal import Processor
    r=record();r.times[4500:r.n]+=.1;r.meta['end']=r.last_time
    x=review_counts(r);sos=Processor(r.config).sos
    np.testing.assert_allclose(x[:4500],sosfiltfilt(sos,r.raw[:4500].astype(float),axis=0))
    np.testing.assert_allclose(x[4500:],sosfiltfilt(sos,r.raw[4500:r.n].astype(float),axis=0))
    assert not x.flags.writeable and review_counts(r) is x
    r.raw[1000,0]+=40;assert review_counts(r) is not x

def test_invalid_contact_cannot_contaminate_neighbouring_review_segment():
    r=record();r.quality[1500:1800]=False;before=review_counts(r).copy();r.raw[1500:1800]=30000
    after=review_counts(r)
    np.testing.assert_array_equal(before[:1500],after[:1500]);np.testing.assert_array_equal(before[1800:],after[1800:])
    np.testing.assert_array_equal(after[1500:1800],r.raw[1500:1800])
    # Only the second channel loses contact; I remains the same filtered signal.
    r=record();before=review_counts(r).copy();r.raw[1500:1800,1]|=1;after=review_counts(r)
    np.testing.assert_array_equal(before[:,0],after[:,0]);assert not np.array_equal(before[:,1],after[:,1])

def test_strict_page_and_square_dimensions_and_no_empty_box():
    r=record();a=automatic_analysis(r,infer=fake_infer,include_models=True);p=page_plan(r,analysis=a)
    assert len(p['rows'])==6
    for row in p['rows']:
        assert row['duration']*25==250 and row['end']-row['start']==10
        assert bool(row['template'])==bool(a['representative'].get(['I','II','III','aVR','aVL','aVF'][row['lead']]))
        if row['template']:
            assert row['template_side']>=24 and row['template_x']+row['template_side']<=291
            # Same amplitude transform for the square and the continuous trace.
            v=np.asarray(row['template']['values_mv']);ys=row['template_baseline']+10*v
            assert np.ptp(ys)==pytest.approx(10*np.ptp(v))
    di=page_plan(r,layout='di',analysis=a)
    assert all(not row['template'] for row in di['rows'][:-1]) and di['rows'][-1]['end']-di['start']==10
    with pytest.raises(ValueError,match='margens|altura'):page_plan(r,analysis=a,imageable=(15,15,267,180))
    with pytest.raises(ValueError,match='escala'):page_plan(r,analysis=a,speed=50)

def test_foreign_window_results_never_print():
    r=record();a=automatic_analysis(r,infer=fake_infer,include_models=True);foreign=copy.deepcopy(a);foreign['scenarios'][0]['first_sample']+=1
    with pytest.raises(ValueError,match='outra janela'):pdf_bytes(r,analysis=foreign)
    foreign=copy.deepcopy(a);foreign['source_key']='other'
    with pytest.raises(ValueError,match='outra captura'):pdf_bytes(r,analysis=foreign)

def test_main_previews_once_after_result_and_retains_full_record(tmp_path,monkeypatch):
    app=QApplication.instance();w=Window(settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat));w.tick_timer.stop();w._analysis_timer.stop()
    r=record();w.recording=r;w.paper.recording=r;w.paper.cursor=r.last_time;a=automatic_analysis(r,infer=fake_infer,include_models=True)
    w.background_result(r,a);app.processEvents();app.processEvents();preview=w._auto_preview
    assert preview is not None and preview.isVisible();assert w.paper.recording.n==r.n and preview.plan['last']-preview.plan['first']==3000
    assert w.paper.analysis is a and w.paper.current_templates();preview.close();app.processEvents()
    w.background_result(r,a);app.processEvents();assert w._auto_preview is None
    b=copy.deepcopy(a);b['run_id']='second-real-run';w.background_result(r,b);app.processEvents();assert w._auto_preview is not None
    w._auto_preview.close();app.processEvents()
    w.recording=record();w.paper.recording=w.recording;w.background_result(r,a);app.processEvents();assert w._auto_preview is None
    w.dirty=False;w.close()

def test_all_bad_quality_calls_no_models_or_qt_and_suppresses_metrics():
    r=record();r.quality[:r.n]=False
    def forbidden(*args):raise AssertionError('Inference forbidden for this input')
    a=automatic_analysis(r,infer=forbidden,qt_infer=forbidden)
    assert a['trace_only'] and a['hypotheses']==[] and a['representative']=={}
    text=PdfReader(io.BytesIO(pdf_bytes(r,analysis=a))).pages[0].extract_text()
    assert 'Somente traçado' in text and 'QTc:' not in text and 'FC:' not in text
