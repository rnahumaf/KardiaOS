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
        preview = PrintPreview(result)
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
