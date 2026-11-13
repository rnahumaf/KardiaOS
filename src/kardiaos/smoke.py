"""Packaged-runtime smoke check, using only generated synthetic data."""
import tempfile
from pathlib import Path
import time
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from bleak.backends.winrt.client import BleakClientWinRT
from .app import Window, synthetic_pairs
from .recording import save_recording, load_recording
from .preview import PrintPreview, render_page, configure_printer, print_page


def check():
    w = Window(demo=True)
    w.tick_timer.stop()
    w.start()
    t = time.monotonic() - 3
    for i in range(0, 900, 9):
        w.accept_samples(t + i / 300, synthetic_pairs(i, 9))
    w.stop()
    assert w.recording.meta['start'] is not None
    assert w.recording.n == 900
    with tempfile.TemporaryDirectory(prefix='kardiaos-synthetic-') as folder:
        path = Path(folder) / 'fixture.kardia'
        save_recording(path, w.recording)
        result = load_recording(path)
        assert result.n == 900 and result.meta['synthetic']
        preview = PrintPreview(result,autostart=False)
        assert not preview.page_image.isNull()
        assert preview.page_image.pixelColor(0, 0).lightness() > 200
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printed = Path(folder) / 'printed-synthetic.pdf'
        printer.setOutputFileName(str(printed))
        configure_printer(printer)
        print_page(preview.data, printer)
        assert not render_page(printed.read_bytes()).isNull()
        preview.close()
    buffer = QBuffer()
    buffer.setData(QByteArray(w.report()))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    doc = QPdfDocument()
    doc.load(buffer)
    assert doc.pageCount() == 1
    doc.close()
    buffer.close()
    w.dirty = False
    w.close()


def check_research():
    """Verify installed assets, GUI imports, worker path and all trained heads."""
    from .recording import Recording
    from .research import analyze, catalog
    from .research_dialog import ResearchDialog
    import numpy as np
    record = Recording(synthetic=True)
    record.append(0, synthetic_pairs(0, 3300), good=True)
    record.meta.update(start=1.0, end=record.last_time)
    dialog = ResearchDialog(record)
    for key, spec in catalog()['models'].items():
        result = analyze(record, key)
        assert result['status'] == 'synthetic', result.get('reasons')
        assert len(result['scores']) == len(spec['labels'])
        assert np.isfinite([v['score'] for v in result['scores']]).all()
    record.meta['synthetic'] = False
    for key in catalog()['models']:
        result = analyze(record, key)
        assert result['status'] == 'inconclusive' and result['scores'] == []
    dialog.close()


def check_automatic():
    from .recording import Recording
    from .automatic_analysis import automatic_analysis,analysis_key
    from .analysis_dialog import AutomaticAnalysisDialog
    from .report import page_plan, pdf_bytes
    from .measurements import measure_recording
    import numpy as np
    record = Recording(synthetic=True)
    record.append(0, synthetic_pairs(0, 9300), good=True)
    record.meta.update(start=1.0, end=record.last_time)
    before = record.raw[:record.n].copy()
    result = automatic_analysis(record)
    assert result['status'] == 'completed'
    assert len(result['scenarios']) == 3
    assert all(v['scores'] and v['status'] == 'synthetic' for v in result['scenarios'])
    np.testing.assert_array_equal(before, record.raw[:record.n])
    dialog = AutomaticAnalysisDialog(record, autostart=False)
    dialog.update_result(dict(kind='measurements', value=result['measurements']))
    for item in result['scenarios']: dialog.update_result(dict(kind='scenario', value=item))
    assert dialog.score_table.rowCount() == 15
    assert measure_recording(None)['metrics']['qtc_f']['value'] is None
    plan = page_plan(record, layout='di')
    assert plan['remaining_seconds'] < .01 and len(plan['rows']) >= 3
    record._automatic_analysis=result;record._automatic_analysis_key=analysis_key(record)
    preview=PrintPreview(record)
    assert preview.analysis['status']=='completed' and preview.save_button.isEnabled()
    assert not preview.page_image.isNull()
    preview.close()
    assert not render_page(pdf_bytes(record, layout='di',analysis=result)).isNull()
    dialog.close()

    # Explicit technical path only; never cached for standard printing.
    technical=automatic_analysis(record,technical_mode=True)
    assert len(technical['scenarios'])==10 and all(v['scores'] for v in technical['scenarios'])
    record.meta['synthetic']=False
    normal=automatic_analysis(record)
    assert not normal['scenarios'] and len(normal['unavailable'])==3
    assert not render_page(pdf_bytes(record,layout='di',analysis=normal)).isNull()
