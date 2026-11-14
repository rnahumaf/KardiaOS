import io
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from kardiaos.automatic_analysis import automatic_analysis,analysis_key
from kardiaos.report import pdf_bytes,page_plan,analysis_for_page
from kardiaos.processing import set_profile,EMPIRICAL,DEFAULT_FILTERS
from test_measurements import signal_record
from test_automatic_analysis import fake_infer

def test_limits_criteria_lead_selection_and_repeated_result(tmp_path):
    app=QApplication.instance() or QApplication([])
    r=signal_record();set_profile(r,EMPIRICAL);r.configure(DEFAULT_FILTERS)
    a=automatic_analysis(r,infer=fake_infer)
    d=AutomaticAnalysisDialog(r,autostart=False);d.resize(850,650);d.show()
    for _ in range(2):
        d.update_result(dict(kind='measurements',value=a['measurements']))
        assert d.lead_selector.count()==2 and d.measure_table.rowCount()==5
        for lead in (0,1):
            d.lead_selector.setCurrentIndex(lead);app.processEvents()
            assert ('DII' if lead else 'DI') in d.measure_note.text()
            assert d.measure_table.item(3,1).text()=='Indisponível'
            assert 'model' in d.measure_table.item(3,2).text() or 'group' in d.measure_table.item(3,2).text()
            assert d.criteria_table.rowCount()==4
            for tab in (0,2,3):
                d.tabs.setCurrentIndex(tab);app.processEvents()
                assert not d.grab().isNull()
            assert d.timing_plot.values is not None and d.beat_selector.count()>=5
    d.close()

def test_print_scope_and_qt_gate_separate_leads():
    r=signal_record();a=automatic_analysis(r,infer=fake_infer)
    for layout in ('di','six'):
        plan=page_plan(r,layout=layout,analysis=a);scoped=analysis_for_page(r,a,plan)
        m=scoped['measurements'];leads=[m]+m['additional_leads']
        assert len(leads)==2  # Technical record retains both native leads; print is compact.
        for v in leads:
            assert v['offset_seconds']+v['duration_seconds']<=plan['end']-plan['begin']+1e-6
            assert v['metrics']['qt']['value'] is None and v['metrics']['qtc_f']['value'] is None
        reader=PdfReader(io.BytesIO(pdf_bytes(r,layout=layout,analysis=a)))
        assert len(reader.pages)==1
        text=reader.pages[0].extract_text()
        assert 'QT:' not in text and 'QTc: erro na estimativa' in text
        assert 'Fase zero' in text and 'Hipóteses dos modelos' in text
        assert len(plan['rows'])==(2 if layout=='di' else 6)

def test_method_policy_and_version_invalidate_old_cache():
    r=signal_record();a=automatic_analysis(r,infer=fake_infer)
    assert a['measurements']['method_version']=='timing-dsp-1'
    assert a['measurements']['qualification']['policy']=='0.7.0'
    assert a['source_key']==analysis_key(r)
