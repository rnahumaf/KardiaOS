import io
import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm
from kardiaos.recording import Recording
from kardiaos.report import pdf_bytes,page_plan
from kardiaos.app import synthetic_pairs

def fixture(single=False):
    r=Recording(synthetic=True);values=synthetic_pairs(0,9301)
    if single:values[:,1]|=1
    r.append(0,values,True);r.meta.update(start=1,end=31);return r

def test_a4_six_synchronized_rows_and_scale():
    r=fixture();plan=page_plan(r);reader=PdfReader(io.BytesIO(pdf_bytes(r)));page=reader.pages[0]
    assert len(reader.pages)==1 and not list(page.images)
    assert float(page.mediabox.width)==pytest.approx(297*mm,abs=.001)
    assert float(page.mediabox.height)==pytest.approx(210*mm,abs=.001)
    assert len(plan['rows'])==6 and {v['duration'] for v in plan['rows']}=={10}
    assert len({(v['first'],v['last']) for v in plan['rows']})==1
    assert {v['data_x'] for v in plan['rows']}=={12}
    assert all(a['top']>b['top'] for a,b in zip(plan['rows'],plan['rows'][1:]))
    assert 'Somente traçado' in page.extract_text() and 'QTc' not in page.extract_text()
    assert 'DADOS SINTÉTICOS' in page.extract_text()

def test_incompatible_width_and_manual_offset_block_without_fitting():
    with pytest.raises(ValueError,match='escala'):pdf_bytes(fixture(),speed=50)
    with pytest.raises(ValueError,match='automática'):pdf_bytes(fixture(),offset=20)

def test_single_contact_report_never_includes_other_leads():
    page=PdfReader(io.BytesIO(pdf_bytes(fixture(single=True)))) .pages[0];text=page.extract_text()
    assert 'DI |' in text
    for token in ('D2','D3','aVF','aVL','aVR'):assert token not in text
