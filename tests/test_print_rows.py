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
    r=signal_record();r.meta['acquisition_mode']='di'
    plan=page_plan(r,speed,gain,raw=True)
    rows=plan['rows'];assert len(rows)==6 and plan['layout']=='di'
    assert [row['duration'] for row in rows] == pytest.approx([5.]*6)
    assert plan['remaining_seconds'] == pytest.approx(0)
    indices=np.concatenate([np.arange(v['first'],v['last']) for v in rows])
    np.testing.assert_array_equal(indices,np.arange(np.searchsorted(r.times[:r.n], r.meta['start']), r.n))
    for i,row in enumerate(rows):
        assert row['data_x']+row['duration']*speed<=plan['content_bounds'][2]
        assert row['top']-row['h']>=23-1e-6
        if i:
            assert rows[i-1]['end']==pytest.approx(row['start'])
            assert rows[i-1]['top']-rows[i-1]['h']>row['top']
    pdf=PdfReader(io.BytesIO(pdf_bytes(r,speed,gain,raw=True)))
    assert len(pdf.pages)==1 and not list(pdf.pages[0].images)
    assert float(pdf.pages[0].mediabox.width)==pytest.approx(297*mm)
    assert float(pdf.pages[0].mediabox.height)==pytest.approx(210*mm)
    text = pdf.pages[0].extract_text()
    assert 'A4 a 100%' in text and all(row['title'] in text for row in rows)


def test_no_silent_vertical_cut_or_time_compression():
    r=signal_record();r.meta['mv_per_count']=1
    with pytest.raises(ValueError,match='ganho'):page_plan(r,gain=20,raw=True,layout='di')
    r=signal_record(seconds=61)
    plan=page_plan(r,speed=50,gain=20,raw=True,layout='di')
    assert plan['end']-plan['start'] == pytest.approx(6 * 274 / 50)
    assert plan['remaining_seconds'] == pytest.approx(60 - 6 * 274 / 50)


def test_di_adapts_to_printer_margins_and_large_amplitude():
    r = signal_record()
    assert len(page_plan(r, layout='di', imageable=(5., 5., 287., 200.))['rows']) == 6
    r.raw[750, 0] = -14000
    area = (12., 10., 273., 190.)
    plan = page_plan(r, gain=20, raw=True, layout='di', imageable=area)
    assert 1 < len(plan['rows']) < 6
    assert plan['end'] - plan['start'] == pytest.approx(30)
    for row in plan['rows']:
        ys = row['baseline'] + plan['values'][row['first']:row['last'], 0] * 20
        assert row['top'] - row['h'] < ys.min() <= ys.max() < row['top']
        assert row['data_x'] + row['duration'] * 25 <= area[0] + area[2]
    assert plan['rows'][-1]['top'] - plan['rows'][-1]['h'] == pytest.approx(area[1] + 20)


def test_di_keeps_printable_window_when_extra_signal_exceeds_page_height():
    r = signal_record()
    r.meta['mv_per_count'] = 1
    r.raw[:r.n, 0] = 0
    r.raw[3400, 0] = 30000  # Just beyond the automatic window, even on a single wide row.
    plan = page_plan(r, gain=20, raw=True, layout='di')
    assert plan['start'] == r.meta['start'] and plan['end'] - plan['start'] == pytest.approx(10)
    assert plan['remaining_seconds'] == pytest.approx(20)


def test_di_explicit_layout_works_with_six_lead_capture_and_preserves_gaps():
    r=signal_record();r.quality[900:960]=False;r.times[5000:r.n]+=.2;r.meta['end']=r.last_time
    plan=page_plan(r,layout='di')
    assert all(v['lead']==0 for v in plan['rows'])
    assert np.isfinite(plan['values'][900:960,0]).all()  # Trace-only fallback retains observed samples.
    page = PdfReader(io.BytesIO(pdf_bytes(r,layout='di'))).pages[0]
    text = page.extract_text()
    assert 'D2' not in text and 'Somente traçado' in text
    row = next(row for row in plan['rows'] if row['first'] < 5000 < row['last'])
    position = ((row['data_x'] + (r.times[5000]-row['start'])*25)*mm,
                (row['baseline'] + plan['values'][5000,0]*10)*mm)
    starts = [tuple(map(float, args)) for args, op in page.get_contents().operations if op == b'm']
    assert any(point == pytest.approx(position, abs=.001) for point in starts)


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
