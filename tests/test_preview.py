import io
import numpy as np
import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication
from PySide6.QtPrintSupport import QPrinter
from kardiaos.preview import PrintPreview,configure_printer,print_page
from kardiaos.automatic_analysis import automatic_analysis,cache_analysis
from test_report import fixture
from test_automatic_analysis import fake_infer

@pytest.mark.parametrize('single', [False, True])
def test_preview_is_opaque_light_and_prints_one_landscape_page(tmp_path, single):
    app=QApplication.instance();r=fixture(single=single);a=automatic_analysis(r,infer=fake_infer);cache_analysis(r,a)
    preview=PrintPreview(r,autostart=False);preview.show();app.processEvents();image=preview.page_image
    if single:
        assert '6 faixas de DI' in preview.span_note.text()
        assert preview.plan['last'] == r.n and preview.plan['end'] - preview.plan['start'] == pytest.approx(30 + 1/300)
    pixels=np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.width(),4)
    assert np.all(pixels[:,:,3]==255) and np.mean(pixels[:,:,:3]>180)>.9
    assert not preview.page.pixmap().isNull() and not hasattr(preview,'offset')
    for w,h in [(1120,850),(800,600)]:
        preview.resize(w,h);app.processEvents();assert preview.rect().contains(preview.print_button.geometry())
        assert preview.page.pixmap().width()<=preview.page.width() and preview.page.pixmap().height()<=preview.page.height()
    printer=QPrinter(QPrinter.PrinterMode.HighResolution);printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    target=tmp_path/'printed-synthetic.pdf';printer.setOutputFileName(str(target));configure_printer(printer)
    assert printer.copyCount()==1;print_page(preview.data,printer,preview.plan['content_bounds'])
    result=PdfReader(target);assert len(result.pages)==1 and float(result.pages[0].mediabox.width)>float(result.pages[0].mediabox.height)
    preview.close()

def test_short_record_and_stale_source_cannot_export():
    r=fixture(single=True);r.n=1800;r.meta['end']=r.last_time
    p=PrintPreview(r,autostart=False);assert not p.data and not p.save_button.isEnabled() and '10 s' in p.status.text();p.close()
    r=fixture();a=automatic_analysis(r,infer=fake_infer);p=PrintPreview(r,analysis=a,autostart=False)
    assert p.ready();r.raw[900,0]+=4;assert not p.ready();p.refresh();assert not p.data;p.close()
