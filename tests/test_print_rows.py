import io
import numpy as np
import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm
from kardiaos.report import page_plan,pdf_bytes
from test_measurements import signal_record


@pytest.mark.parametrize('speed',[25,50])
@pytest.mark.parametrize('gain',[5,10,20])
def test_di_rows_preserve_each_sample_once_and_physical_scales(speed,gain):
    r=signal_record();r.raw[:r.n,1]|=1;r.lead_modes[:r.n]=1
    plan=page_plan(r,speed,gain,raw=True,layout='di')
    rows=plan['rows'];assert len(rows)>=2
    indices=np.concatenate([np.arange(v['first'],v['last']) for v in rows])
    np.testing.assert_array_equal(indices,np.arange(rows[0]['first'],rows[-1]['last']))
    for i,row in enumerate(rows):
        assert row['data_x']+(row['end']-row['start'])*speed<=row['x']+row['w']+1e-6
        assert row['top']-row['h']>=30-1e-6
        if i:
            assert rows[i-1]['end']==pytest.approx(row['start'])
            assert rows[i-1]['top']-rows[i-1]['h']>row['top']
    pdf=PdfReader(io.BytesIO(pdf_bytes(r,speed,gain,raw=True,layout='di')))
    assert len(pdf.pages)==1 and not list(pdf.pages[0].images)
    assert float(pdf.pages[0].mediabox.width)==pytest.approx(297*mm)
    assert float(pdf.pages[0].mediabox.height)==pytest.approx(210*mm)
    assert 'A4 a 100%' in pdf.pages[0].extract_text()
    if speed==25:assert plan['remaining_seconds']==pytest.approx(20)


def test_no_silent_vertical_cut_or_time_compression():
    r=signal_record();r.meta['mv_per_count']=1
    with pytest.raises(ValueError,match='ganho'):page_plan(r,gain=20,raw=True,layout='di')
    r=signal_record(seconds=61)
    plan=page_plan(r,speed=50,gain=20,raw=True,layout='di')
    assert plan['remaining_seconds']>0
    assert all(row['duration']==5 for row in plan['rows'])


def test_di_explicit_layout_works_with_six_lead_capture_and_preserves_gaps():
    r=signal_record();r.quality[900:960]=False;r.times[5000:r.n]+=.2;r.meta['end']=r.last_time
    plan=page_plan(r,layout='di')
    assert all(v['lead']==0 for v in plan['rows'])
    assert np.isfinite(plan['values'][900:960,0]).all()  # Trace-only fallback retains observed samples.
    text=PdfReader(io.BytesIO(pdf_bytes(r,layout='di'))).pages[0].extract_text()
    assert 'D2' not in text and 'Somente traçado' in text


@pytest.mark.parametrize('speed',[25,50])
def test_pdf_calibration_pulse_has_real_200ms_width(speed):
    page=PdfReader(io.BytesIO(pdf_bytes(signal_record(),speed=speed,layout='di'))).pages[0]
    paths=[];points=[]
    for operands,operation in page.get_contents().operations:
        if operation==b'm':points=[tuple(map(float,operands))]
        elif operation==b'l':points.append(tuple(map(float,operands)))
        elif operation==b'S':
            if len(points)==6:paths.append(points)
            points=[]
    assert paths
    pulse=paths[0]
    assert pulse[3][0]-pulse[2][0]==pytest.approx(.2*speed*mm,abs=.001)
    assert pulse[2][1]-pulse[1][1]==pytest.approx(10*mm,abs=.001)
    assert not any(op in [b'W',b'W*'] for _,op in page.get_contents().operations)
