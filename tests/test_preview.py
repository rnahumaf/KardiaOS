import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import io
import numpy as np
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication
from PySide6.QtPrintSupport import QPrinter
from kardiaos.preview import PrintPreview, configure_printer, print_page
from test_report import fixture


def test_preview_is_opaque_light_and_prints_one_landscape_page(tmp_path):
    app = QApplication.instance() or QApplication([])
    preview = PrintPreview(fixture())
    preview.show()
    app.processEvents()
    image = preview.page_image
    pixels = np.frombuffer(image.bits(), dtype=np.uint8).reshape(image.height(), image.width(), 4)
    assert np.all(pixels[:, :, 3] == 255)
    assert np.mean(pixels[:, :, :3] > 180) > .9
    assert not preview.page.pixmap().isNull()
    before = preview.data
    preview.offset.setValue(15)
    assert preview.data != before
    assert 'Trecho 15.0 a 25.0 s' in PdfReader(io.BytesIO(preview.data)).pages[0].extract_text()
    for width, height in [(1120, 850), (800, 600)]:
        preview.resize(width, height)
        app.processEvents()
        assert preview.rect().contains(preview.print_button.geometry())
        assert preview.page.pixmap().width() <= preview.page.width()
        assert preview.page.pixmap().height() <= preview.page.height()
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    target = tmp_path / 'printed-synthetic.pdf'
    printer.setOutputFileName(str(target))
    configure_printer(printer)
    assert printer.copyCount() == 1
    print_page(preview.data, printer)
    result = PdfReader(target)
    assert len(result.pages) == 1
    assert float(result.pages[0].mediabox.width) > float(result.pages[0].mediabox.height)
    preview.close()


def test_excerpt_control_cannot_exceed_last_sample():
    app = QApplication.instance() or QApplication([])
    r = fixture(single=True)
    r.n -= 1
    r.meta['end'] = r.last_time
    preview = PrintPreview(r)
    preview.offset.setValue(preview.offset.maximum())
    assert preview.offset.value() < r.last_time - r.meta['start']
    assert len(PdfReader(io.BytesIO(preview.data)).pages) == 1
    preview.close()
