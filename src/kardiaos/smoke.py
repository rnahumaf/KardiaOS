"""Installed-runtime checks. Synthetic-only; isolated settings; no visible window."""
import tempfile,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtPrintSupport import QPrinter
from bleak.backends.winrt.client import BleakClientWinRT
from .app import Window,synthetic_pairs
from .recording import Recording,save_recording,load_recording
from .preview import PrintPreview,render_page,configure_printer,print_page


def check():
    from .automatic_analysis import analysis_key
    from .review_window import trace_window
    from .measurements import empty
    with tempfile.TemporaryDirectory(prefix='kardiaos-synthetic-') as folder:
        w=Window(demo=True,settings=QSettings(str(Path(folder)/'prefs.ini'),QSettings.Format.IniFormat));w.tick_timer.stop();w.start()
        t=time.monotonic()-12
        for i in range(0,3600,9):w.accept_samples(t+i/300,synthetic_pairs(i,9))
        w.stop();assert w.recording.n==3600 and w.recording.meta['start'] is not None
        path=Path(folder)/'fixture.kardia';save_recording(path,w.recording);r=load_recording(path)
        assert r.n==3600 and r.meta['synthetic']
        analysis=dict(status='completed',mode='normal',source_key=analysis_key(r),report_window=trace_window(r),reportable=True,trace_only=True,
            measurements=empty('Synthetic rendering check'),scenarios=[],hypotheses=[],representative={})
        preview=PrintPreview(r,analysis=analysis,autostart=False)
        assert preview.page_image is not None and not preview.page_image.isNull() and preview.ready()
        assert preview.page_image.pixelColor(0,0).lightness()>200
        printer=QPrinter(QPrinter.PrinterMode.HighResolution);printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printed=Path(folder)/'printed.pdf';printer.setOutputFileName(str(printed));configure_printer(printer)
        print_page(preview.data,printer,preview.plan['content_bounds']);assert not render_page(printed.read_bytes()).isNull()
        preview.close();assert not render_page(w.report()).isNull();w.dirty=False;w.close()


def check_research():
    from .research import analyze,catalog
    from .research_dialog import ResearchDialog
    record=Recording(synthetic=True);record.append(0,synthetic_pairs(0,3300),good=True);record.meta.update(start=1.,end=record.last_time)
    dialog=ResearchDialog(record)
    for key,spec in catalog()['models'].items():
        result=analyze(record,key);assert result['status']=='synthetic',result.get('reasons')
        assert len(result['scores'])==len(spec['labels']) and np.isfinite([v['score'] for v in result['scores']]).all()
    record.meta['synthetic']=False
    for key in catalog()['models']:
        result=analyze(record,key);assert result['status']=='inconclusive' and result['scores']==[]
    dialog.close()


def check_automatic():
    from .automatic_analysis import automatic_analysis,cache_analysis
    from .analysis_dialog import AutomaticAnalysisDialog
    from .report import page_plan,pdf_bytes
    from .processing import set_profile,EMPIRICAL,REFERENCED,DEFAULT_FILTERS
    record=Recording(synthetic=True);record.append(0,synthetic_pairs(0,9300),good=True);record.meta.update(start=1.,end=record.last_time)
    before=record.raw[:record.n].copy();set_profile(record,EMPIRICAL);record.configure(DEFAULT_FILTERS)
    began=time.perf_counter()
    result=automatic_analysis(record)
    assert result['status']=='completed' and not result['scenarios'] and result['classification']['version']=='limb-rules-1'
    assert all(v['scores'] and v['status']=='synthetic' for v in result['scenarios'])
    assert result['qt']['source']=='global_medians_only' and not result['qt']['neural_segmenter_used']
    assert len(result['representative'])==6
    assert not result['clinical_validation'] and result['exploratory_policy']['confidence_calibrated'] is False
    assert result['qtc_label']=='QTc global: indisponível' or 'Fridericia; baixa confiança)' in result['qtc_label']
    np.testing.assert_array_equal(before,record.raw[:record.n]);cache_analysis(record,result)
    dialog=AutomaticAnalysisDialog(record,autostart=False);dialog.update_result(dict(kind='measurements',value=result['measurements']));dialog.on_result(result)
    from PySide6.QtWidgets import QApplication
    dialog.show();QApplication.processEvents();assert not dialog.grab().isNull()
    elapsed=time.perf_counter()-began
    assert elapsed<2, f'Rules and rendered UI exceeded target: {elapsed:.3f} s'
    assert dialog.score_table.rowCount()>=17 and dialog.score_table.columnCount()==2 and dialog.lead_selector.count()==6
    assert dialog.criteria_table.rowCount()>=2 and not dialog.beat_selector.isVisible()
    for measured in [result['measurements']]+result['measurements']['additional_leads']:
        assert measured['pipeline']['source']=='aligned_medians_only' and measured['global_intervals']
        assert measured['method_version']=='global-median-3'
        assert measured['pipeline']['detector_source']=='displayed_smoothed_medians'
        median=measured['median'];original_median=np.asarray(median['unsmoothed_values_mv'])
        assert max(abs(np.asarray(median['values_mv'])-original_median)) <= .015*np.ptp(original_median)+1e-12
        assert measured['global_fiducials']==result['measurements']['global_fiducials']
        if measured['metrics']['qtc_f']['value'] is not None:assert measured['metrics']['qtc_f']['status']=='exploratory_low_confidence'
    plan=page_plan(record,analysis=result);assert len(plan['rows'])==6 and plan['end']-plan['start']==10
    di=page_plan(record,layout='di',analysis=result);assert len(di['rows'])==2 and all(not v['template'] for v in di['rows'][:-1])
    preview=PrintPreview(record);assert preview.thread is None and preview.ready() and not preview.page_image.isNull();preview.close()
    assert not render_page(pdf_bytes(record,layout='di',analysis=result)).isNull();dialog.close()
    # The optional referenced profile still requires channel-specific evidence.
    set_profile(record,REFERENCED);record.meta['synthetic']=False
    normal=automatic_analysis(record);assert not normal['scenarios'] and normal['classification']
    assert normal['qt']['source']=='global_medians_only'
    assert not render_page(pdf_bytes(record,layout='di',analysis=normal)).isNull()
    return dict(analysis_and_ui_seconds=round(elapsed,3))
