"""Installed-runtime checks. Synthetic-only; isolated settings; no visible window."""
import tempfile,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtPrintSupport import QPrinter,QPrinterInfo
from bleak.backends.winrt.client import BleakClientWinRT
from .app import Window,synthetic_pairs
from .recording import Recording,save_recording,load_recording
from .preview import PrintPreview,render_page,configure_printer,print_page
from .report import DEFAULT_IMAGEABLE


class OfflinePreview(PrintPreview):
    """Use PDF margins so a synthetic check never probes a physical queue."""

    def imageable(self):
        return DEFAULT_IMAGEABLE


def check():
    from .automatic_analysis import analysis_key
    from .review_window import trace_window
    from .measurements import empty
    with tempfile.TemporaryDirectory(prefix='kardiaos-synthetic-') as folder:
        w=Window(demo=True,settings=QSettings(str(Path(folder)/'prefs.ini'),QSettings.Format.IniFormat));w.tick_timer.stop();w.start()
        t=time.monotonic()-12
        for i in range(0,3600,9):w.accept_samples(t+i/300,synthetic_pairs(i,9))
        w.stop();w._analysis_timer.stop();assert w.recording.n==3600 and w.recording.meta['start'] is not None
        path=Path(folder)/'fixture.kardia';save_recording(path,w.recording);r=load_recording(path)
        assert r.n==3600 and r.meta['synthetic']
        analysis=dict(status='completed',mode='normal',source_key=analysis_key(r),report_window=trace_window(r),reportable=True,trace_only=True,
            measurements=empty('Synthetic rendering check'),scenarios=[],hypotheses=[],representative={})
        preview=OfflinePreview(r,analysis=analysis,autostart=False)
        assert preview.page_image is not None and not preview.page_image.isNull() and preview.ready()
        assert preview.page_image.pixelColor(0,0).lightness()>200
        pdf_device = QPrinterInfo.printerInfo('Microsoft Print to PDF')
        if not pdf_device.isNull():
            printer = QPrinter(pdf_device, QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printed = Path(folder)/'printed.pdf'
            printer.setOutputFileName(str(printed))
            configure_printer(printer)
            print_page(preview.data, printer, preview.plan['content_bounds'])
            assert not render_page(printed.read_bytes()).isNull()
        preview.close();assert not render_page(w.report()).isNull();w.dirty=False;w.close()
        return dict(pdf_printer_exercised=not pdf_device.isNull())


def check_research():
    from PySide6.QtWidgets import QApplication
    from .research import catalog
    from .research_dialog import ResearchDialog
    record=Recording(synthetic=True);record.append(0,synthetic_pairs(0,3300),good=True);record.meta.update(start=1.,end=record.last_time)
    # Synthetic samples deliberately carry no synthetic exemption or references.
    # Exercise the real dialog queue and worker, including raw input provenance.
    record.meta['synthetic']=False
    dialog=ResearchDialog(record);dialog.show()
    deadline=time.monotonic()+600
    try:
        while not all(p.result is not None for p in dialog.panes) or dialog.busy():
            QApplication.processEvents()
            if time.monotonic()>deadline:raise AssertionError('Neural dialog did not finish within 600 s')
            time.sleep(.01)
        for pane in dialog.panes:
            result=pane.result;spec=catalog()['models'][pane.key]
            assert result['status']=='experimental',result.get('reasons')
            assert len(result['scores'])==len(spec['labels']) and np.isfinite([v['score'] for v in result['scores']]).all()
            assert pane.table.rowCount()==len(spec['labels']) and pane.run_button.isEnabled()
            assert result['input_contract']['source']=='raw' and result['input_contract']['amplitude_multiplier']==1
            assert not result['calibration_verified'] and not result['clinical_validation']
            assert result['evidence']['decoder']=={'I':None,'II':None}
        assert dialog.offset.isEnabled() and dialog.run_all.isEnabled()
        return dict(neural_models={p.key:p.table.rowCount() for p in dialog.panes})
    finally:
        # Do not destroy QThreads if the smoke assertion fails during execution.
        dialog.pending.clear()
        for pane in dialog.panes:
            if pane.thread is not None:pane.thread.wait(190000)
        QApplication.processEvents()
        dialog.close()


def check_automatic():
    from .automatic_analysis import automatic_analysis,cache_analysis
    from .analysis_dialog import AutomaticAnalysisDialog
    from .report import page_plan,pdf_bytes
    from .processing import set_profile,EMPIRICAL,REFERENCED,DEFAULT_FILTERS
    from .rule_analysis import VERSION as RULE_VERSION
    from .global_median import VERSION as MEDIAN_VERSION
    record=Recording(synthetic=True);record.append(0,synthetic_pairs(0,9300),good=True);record.meta.update(start=1.,end=record.last_time)
    before=record.raw[:record.n].copy();set_profile(record,EMPIRICAL);record.configure(DEFAULT_FILTERS)
    began=time.perf_counter()
    result=automatic_analysis(record)
    assert result['status']=='completed' and not result['scenarios'] and result['classification']['version']==RULE_VERSION
    assert all(v['scores'] and v['status']=='synthetic' for v in result['scenarios'])
    assert result['qt']['source']=='global_medians_only' and not result['qt']['neural_segmenter_used']
    assert len(result['representative'])==6
    assert not result['clinical_validation'] and result['exploratory_policy']['confidence_calibrated'] is False
    assert result['qtc_label']=='QTc global: indisponível' or 'Fridericia)' in result['qtc_label']
    np.testing.assert_array_equal(before,record.raw[:record.n]);cache_analysis(record,result)
    dialog=AutomaticAnalysisDialog(record,autostart=False);dialog.update_result(dict(kind='measurements',value=result['measurements']));dialog.on_result(result)
    from PySide6.QtWidgets import QApplication
    dialog.show();QApplication.processEvents();assert not dialog.grab().isNull()
    elapsed=time.perf_counter()-began
    assert elapsed<2, f'Rules and rendered UI exceeded target: {elapsed:.3f} s'
    assert sum(table.rowCount() for table in dialog.rule_tables.values())>=18 and dialog.lead_selector.count()==6
    assert dialog.criteria_table.rowCount()>=2 and not dialog.beat_selector.isVisible()
    for rule in result['classification']['rules']:
        dialog.open_evidence(rule['id']);QApplication.processEvents()
        assert dialog.evidence_panel.data['key']==rule['id'] and not dialog.evidence_panel.plot.grab().isNull()
    dialog.show_all_curves();dialog.tabs.setCurrentIndex(0)
    for measured in [result['measurements']]+result['measurements']['additional_leads']:
        assert measured['pipeline']['source']=='aligned_medians_only' and measured['global_intervals']
        assert measured['method_version']==MEDIAN_VERSION
        assert measured['pipeline']['detector_source']=='displayed_smoothed_medians'
        median=measured['median'];original_median=np.asarray(median['unsmoothed_values_mv'])
        assert max(abs(np.asarray(median['values_mv'])-original_median)) <= .015*np.ptp(original_median)+1e-12
        assert measured['global_fiducials']==result['measurements']['global_fiducials']
        if measured['metrics']['qtc_f']['value'] is not None:assert measured['metrics']['qtc_f']['status']=='estimated'
    plan=page_plan(record,analysis=result);assert len(plan['rows'])==6 and plan['end']-plan['start']==10
    di=page_plan(record,layout='di',analysis=result);assert len(di['rows'])==2 and all(not v['template'] for v in di['rows'][:-1])
    preview=OfflinePreview(record);assert preview.thread is None and preview.ready() and not preview.page_image.isNull();preview.close()
    assert not render_page(pdf_bytes(record,layout='di',analysis=result)).isNull();dialog.close()
    # The optional referenced profile still requires channel-specific evidence.
    set_profile(record,REFERENCED);record.meta['synthetic']=False
    normal=automatic_analysis(record);assert not normal['scenarios'] and normal['classification']
    assert normal['qt']['source']=='global_medians_only'
    assert not render_page(pdf_bytes(record,layout='di',analysis=normal)).isNull()
    return dict(analysis_and_ui_seconds=round(elapsed,3))
