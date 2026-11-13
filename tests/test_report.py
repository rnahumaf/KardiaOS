import io
import numpy as np
import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm
from kardiaos.recording import Recording
from kardiaos.report import pdf_bytes
from kardiaos.app import synthetic_pairs


def fixture(single=False):
    r = Recording(synthetic=True)
    values = synthetic_pairs(0, 9301)
    if single:
        values[:, 1] |= 1
    r.append(0, values, True)
    r.meta.update(start=1, end=31)
    return r


@pytest.mark.parametrize('speed', [25, 50])
@pytest.mark.parametrize('offset', [0, 20])
def test_a4_landscape_single_page_and_scale(speed, offset):
    pdf = PdfReader(io.BytesIO(pdf_bytes(fixture(), speed=speed, offset=offset)))
    assert len(pdf.pages) == 1
    for page in pdf.pages:
        assert abs(float(page.mediabox.width) - 297 * mm) < .001
        assert abs(float(page.mediabox.height) - 210 * mm) < .001
        text = page.extract_text()
        for token in ('D2 contínua', f'{speed} mm/s', '10 mm/mV', 'DADOS SINTÉTICOS', 'nao calibrada', 'Página 1/1'):
            assert token in text
        assert len(page.images) == 0  # Waveforms and grid are vector paths.
        labels = {}
        def visit(text, cm, tm, font, size):
            if text.strip() in ('D1', 'D2', 'D3', 'aVF', 'aVL', 'aVR', 'D2 contínua'):
                labels[text.strip()] = tm[4:6]
        page.extract_text(visitor_text=visit)
        for left, right in [('D1', 'aVF'), ('D2', 'aVL'), ('D3', 'aVR')]:
            assert labels[left][0] < labels[right][0]
            assert labels[left][1] == labels[right][1]
        assert labels['D1'][1] > labels['D2'][1] > labels['D3'][1] > labels['D2 contínua'][1]


def test_single_contact_report_never_includes_other_leads():
    page = PdfReader(io.BytesIO(pdf_bytes(fixture(single=True)))).pages[0]
    text = page.extract_text()
    assert 'Somente D1' in text
    for token in ('D2', 'D3', 'aVF', 'aVL', 'aVR'):
        assert token not in text
