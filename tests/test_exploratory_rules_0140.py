import numpy as np
import pytest
from kardiaos.rule_analysis import classify,features,DESCRIPTIONS
from kardiaos.morphology_rules import describe_wave
from kardiaos.analysis_presentation import descriptive_messages
from test_rule_analysis import case,status
from test_measurement_quality import coherent_quality,known


def row(c,key):return next(v for v in c['rules'] if v['id']==key)


def test_unreferenced_amplitude_and_missing_age_use_explicit_assumptions():
    r,m,reps=case();r.meta['synthetic']=False;r.meta['clinical_context']={}
    before=r.raw.copy();data=features(m,reps);data['II']['p_mv']=.3
    c=classify(r,m,reps,feature_data=data);v=row(c,'p_tall')
    assert v['status']=='detected' and v in c['findings']
    assert any('Idade não informada' in s for s in v['limitations'])
    assert any('Convenção elétrica' in s for s in v['limitations'])
    assert any('calibração não validada' in s for s in v['limitations'])
    assert status(c,'brady')=='unavailable' and status(c,'qt_long')=='unavailable'
    np.testing.assert_array_equal(r.raw,before)
    r.meta['clinical_context']['age_years']=10
    assert status(classify(r,m,reps,feature_data=data),'p_tall')=='unavailable'


def test_instability_never_discards_a_full_median_amplitude_finding():
    r,m,reps=case();data=features(m,reps);data['II']['p_mv']=.3
    m['technical_quality']=coherent_quality(m,reps)
    for b in m['technical_quality']['boundaries'].values():
        b.update(status='review',contrast=5,detected_subsets=2,reason='Marco instável.')
    c=classify(r,m,reps,feature_data=data);v=row(c,'p_tall')
    assert v['status']=='detected' and v['central_status']=='detected' and v in c['findings']
    assert v['technical_status']=='advisory' and 'Marco instável.' in v['limitations']
    assert status(c,'pr_long')=='unavailable'


def test_subset_only_amplitude_is_visible_but_does_not_change_summary():
    r,m,reps=case();baseline=classify(r,m,reps);m['technical_quality']=coherent_quality(m,reps)
    for lead in ('I','aVL'):m['technical_quality']['replicates'][0]['features'][lead]['j_mv']=.15
    c=classify(r,m,reps);v=row(c,'j_elevation')
    assert v['status']=='not_detected' and v['possible']['leads']==['I','aVL']
    assert c['summary']==baseline['summary'] and not c['findings'] and v in c['possibilities']
    assert 'Possível Elevação' in descriptive_messages(c)[1][0]


def test_contiguous_leads_cannot_be_assembled_from_different_subsets():
    r,m,reps=case();m['technical_quality']=coherent_quality(m,reps)
    m['technical_quality']['replicates'][0]['features']['I']['j_mv']=.15
    m['technical_quality']['replicates'][1]['features']['aVL']['j_mv']=.15
    assert 'possible' not in row(classify(r,m,reps),'j_elevation')


@pytest.mark.parametrize('change',[('ton',-40),('ton',20)])
def test_subset_t_onset_is_audited_but_fixed_for_feature_comparison(monkeypatch,change):
    r,m,reps,q=known(monkeypatch,shift=change)
    assert q['replicates'][0]['points']['ton']!=m['global_fiducials']['ton']
    assert all(v['analysis_points']['ton']==m['global_fiducials']['ton'] for v in q['replicates'])
    assert all(v['features']['I']['st60_mv'] is not None for v in q['replicates'])
    assert q['boundaries']['ton']['status']=='review'
    c=classify(r,m,reps)
    assert status(c,'st_depression')=='not_detected'


@pytest.mark.parametrize('kind,weak',[('p',.018),('t',.025)])
@pytest.mark.parametrize('sign',[1,-1])
def test_biphasic_clear_and_discrete_components(kind,weak,sign):
    x=np.arange(81)
    y=.2*np.exp(-((x-25)/7)**2)-weak*np.exp(-((x-55)/7)**2)
    assert describe_wave(sign*y,.001,kind)['biphasic']['status']=='possible'
    y=.2*np.exp(-((x-25)/7)**2)-.09*np.exp(-((x-55)/7)**2)
    evidence=describe_wave(sign*y,.001,kind)['biphasic']
    assert evidence['status']=='detected' and len(evidence['components'])==2


def test_monophasic_wave_and_single_sample_spike_are_not_biphasic():
    x=np.arange(81);y=.2*np.exp(-((x-25)/7)**2)
    assert describe_wave(y,.001,'p')['biphasic']['status']=='not_detected'
    y[65]=-.04
    assert describe_wave(y,.001,'p')['biphasic']['status']=='not_detected'


def test_notch_requires_two_same_polarity_lobes_and_a_valley():
    x=np.arange(91)
    one=.3*np.exp(-((x-42)/14)**2)
    assert describe_wave(one,.001,'t')['notched']['status']=='not_detected'
    two=.25*np.exp(-((x-28)/9)**2)+.23*np.exp(-((x-54)/9)**2)
    for sign in (1,-1):
        shape=describe_wave(sign*two,.001,'t')['notched']
        assert shape['status']=='detected' and len(shape['components'])==3
    assert describe_wave(two,.15,'t')['notched']['status']=='not_detected'


def test_descriptive_shapes_never_enter_main_findings_or_veto_sinus_alone():
    r,m,reps=case();data=features(m,reps);baseline=classify(r,m,reps)
    for key in DESCRIPTIONS:data['I'][key]=True
    data['II']['t_biphasic_possible']=True
    c=classify(r,m,reps,feature_data=data)
    assert c['summary']==baseline['summary'] and c['sinus_supported']
    assert not c['findings'] and len(c['morphology'])==3
    texts=descriptive_messages(c)[0]
    assert any('Possível T bifásica — II' in s for s in texts)


def test_missing_wave_is_still_unavailable_not_fabricated():
    r,m,reps=case();m['global_fiducials'].pop('toff')
    c=classify(r,m,reps)
    assert status(c,'t_tall')=='unavailable' and status(c,'t_biphasic')=='unavailable'
    assert status(c,'p_tall')=='not_detected'


def test_details_show_possibilities_without_leaking_into_main_findings():
    from PySide6.QtWidgets import QApplication
    from kardiaos.analysis_dialog import AutomaticAnalysisDialog
    from kardiaos.automatic_analysis import automatic_analysis
    from test_rule_analysis import signal_record
    app=QApplication.instance();r=signal_record();a=automatic_analysis(r)
    c=a['classification'];v=row(c,'j_elevation')
    v['possible']=dict(source='subset_medians',leads=['I','aVL'],subsets=['primeira metade'],reason='Presente apenas em subconjuntos.')
    row(c,'p_biphasic')['possible_morphology_leads']=['II']
    v['limitations']=['Idade não informada: comparação exploratória com limiares de adulto.']
    d=AutomaticAnalysisDialog(r,autostart=False);d.on_result(a);d.show();app.processEvents()
    assert d.possibilities_label.isVisible() and 'primeira metade' in d.possibilities_label.text()
    assert 'Possível P bifásica' in d.morphology_label.text()
    assert 'Idade não informada' in d.limitations_label.text()
    assert 'primeira metade' not in d.findings_label.text()
    assert 'Possível P bifásica' not in d.classification_summary.text()
    d.close()
