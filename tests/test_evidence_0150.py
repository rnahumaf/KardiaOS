import json
import numpy as np
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from kardiaos.rule_analysis import classify
from kardiaos.evidence_view import evidence_data
from kardiaos.automatic_analysis import automatic_analysis
from kardiaos.analysis_dialog import AutomaticAnalysisDialog
from test_rule_analysis import case,status
from test_measurements import signal_record
from test_measurement_quality import coherent_quality


def row(c,key):return next(v for v in c['rules'] if v['id']==key)


@pytest.mark.parametrize('qtc,expected,possible',[(449.9,'not_detected',False),(450,'not_detected',True),(459.9,'not_detected',True),(460,'detected',False)])
def test_qtc_without_sex_compares_both_thresholds(qtc,expected,possible):
    r,m,reps=case();r.meta['clinical_context']={};m['metrics']['qtc_f']['value']=qtc
    c=classify(r,m,reps);v=row(c,'qt_long')
    assert v['status']==expected and bool(v.get('possible_context'))==possible
    assert bool(v in c['findings'])==(expected=='detected')
    assert any('450 ms' in s and '460 ms' in s for s in v['limitations'])


def test_no_reference_sinus_is_explicit_assumption_without_mutation():
    r,m,reps=case();r.meta['synthetic']=False;r.meta['clinical_context']={};raw=r.raw.copy()
    c=classify(r,m,reps)
    assert c['sinus_supported'] and c['status']=='no_findings' and not c['missing']
    assert c['sinus_limitations']
    np.testing.assert_array_equal(raw,r.raw)
    m['alignment']['excluded']=[dict(sample=1800)]
    assert not classify(r,m,reps)['sinus_supported']


def test_unavailable_qtc_cannot_be_resurrected_by_subset():
    r,m,reps=case();m['technical_quality']=coherent_quality(m,reps)
    m['metrics']['qtc_f'].update(value=None,reason='RR instáveis')
    for replica in m['technical_quality']['replicates']:replica['values']['qtc_f']=500
    c=classify(r,m,reps);v=row(c,'qt_long')
    assert v['status']=='unavailable' and 'possible' not in v and v['reason']=='RR instáveis'


def test_interval_instability_preserves_positive_full_median():
    r,m,reps=case();m['metrics']['pr']['value']=205;m['technical_quality']=coherent_quality(m,reps)
    m['technical_quality']['replicates'][0]['values']['pr']=195
    c=classify(r,m,reps);v=row(c,'pr_long')
    assert v['status']=='detected' and v in c['findings'] and v['limitations']


def test_evidence_uses_exact_full_and_subset_curve_values_and_markers():
    r=signal_record();a=automatic_analysis(r);json.dumps(a,allow_nan=False)
    q=a['measurements']['technical_quality'];assert q['replicates']
    for source in (-1,0,1,2,3):
        for key in ('p_tall','t_tall','j_elevation','st_depression','p_biphasic','t_notched','q_prominent','pr_long','qt_long'):
            d=evidence_data(r,a,key,source)
            curves=a['representative'] if source<0 else q['replicates'][source]['curves']
            features=a['classification']['features'] if source<0 else q['replicates'][source]['features']
            for t in d['traces']:
                pt=key.startswith('p_') or key.startswith('t_');f=features[t['lead']]
                expected=np.asarray(curves[t['lead']]['pt_values_mv' if pt else 'values_mv'])-f['pt_baseline_mv' if pt else 'baseline_mv']
                np.testing.assert_array_equal(t['y'],expected)
                assert all(0<=v['index']<len(expected) and np.isfinite(v['value']) for v in t['markers'])
                if key=='j_elevation' and t['markers']:assert t['markers'][0]['value']==f['j_mv']
                if key=='st_depression' and t['markers']:assert t['markers'][0]['value']==f['st60_mv']
    assert all(v['analysis_points']['ton']==a['measurements']['global_fiducials']['ton'] for v in q['replicates'])


def test_rr_pairs_match_computed_values_and_do_not_cross_gap():
    r=signal_record();r.times[4500:r.n]+=2
    a=automatic_analysis(r);rhythm=a['measurements']['alignment']['rhythm']
    assert len(rhythm['rr_pairs'])==len(rhythm['rr_seconds'])
    for (left,right),rr in zip(rhythm['rr_pairs'],rhythm['rr_seconds']):
        assert not left<4500<=right
        assert (right-left)/300==pytest.approx(rr)


def test_click_navigation_subset_switch_and_return(qt_application):
    r=signal_record();a=automatic_analysis(r);v=row(a['classification'],'p_tall')
    v['possible']=dict(source='subset_medians',leads=['II'],subsets=['primeira metade','segunda metade'],reason='Somente subconjuntos.')
    d=AutomaticAnalysisDialog(r,autostart=False);d.update_result(dict(kind='measurements',value=a['measurements']));d.on_result(a);d.resize(850,650);d.show();qt_application.processEvents()
    d.possibilities_label.linkActivated.emit('p_tall');qt_application.processEvents()
    e=d.evidence_panel
    assert d.tabs.currentIndex()==2 and e.isVisible() and not d.curve_overview.isVisible()
    assert e.source_selector.count()==3 and e.data['subset']==0
    e.source_selector.setCurrentIndex(2);assert e.data['subset']==1
    e.back.click();assert d.curve_overview.isVisible() and not e.isVisible()
    index=next(i for i in range(d.score_table.rowCount()) if d.score_table.item(i,0).data(Qt.ItemDataRole.UserRole)=='irregular')
    d.open_table_evidence(index,0);qt_application.processEvents()
    assert e.data['key']=='irregular' and e.range_row.isVisible()
    e.plot.grab();target=e.plot.rr_targets[-2]
    QTest.mouseClick(e.plot,Qt.MouseButton.LeftButton,pos=QPoint(round(target[0]),round(target[1])))
    assert e.rhythm_offset.value()>0
    assert d.rect().contains(d.export_button.geometry())
    d.close()


def test_empty_analysis_has_no_stale_evidence(qt_application):
    r=signal_record();a=automatic_analysis(r);d=AutomaticAnalysisDialog(r,autostart=False);d.on_result(a);d.open_evidence('t_tall')
    d.on_result(dict(status='completed',classification={},measurements={}))
    assert d.evidence_panel.rule_selector.count()==0 and d.curve_overview.isHidden() is False
    d.close()


def test_negative_rule_evidence_only_shows_eligible_leads():
    r=signal_record();a=automatic_analysis(r)
    for key,expected in [('p_tall',{'II','III','aVF'}),('q_prominent',{'I','II','aVL','aVF'}),('t_inversion',{'I','II','III','aVL','aVF'})]:
        assert {v['lead'] for v in evidence_data(r,a,key)['traces']}==expected
