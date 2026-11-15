"""Synthetic P transitions, exact QTc gates and compact-table regressions."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from kardiaos.median_landmarks import p_offset,combine_candidates,wave_candidate
from kardiaos.global_median import qtc_blockers
from kardiaos.rule_analysis import classify
from test_rule_analysis import case
from test_main_flows_0110 import window,attach
from test_measurements import signal_record
from kardiaos.automatic_analysis import automatic_analysis


@pytest.mark.parametrize('sign',[1,-1])
@pytest.mark.parametrize('shift',[0,15])
@pytest.mark.parametrize('gain',[.4,2.])
def test_p_offset_tracks_baseline_transition_with_drift_and_polarity(sign,shift,gain):
    t=np.arange(140)-shift
    x=np.where(t<=65,1-.04*(t-40),.001*(t-65))
    x=sign*gain*x+4
    off,reason,evidence=p_offset(x,40+shift,100+shift,sign,.001*gain,65+shift)
    assert not reason and off==65+shift
    assert evidence['transition_indices']==[65+shift,65+shift]


def test_p_offset_requires_transition_and_tangent_agreement():
    x=1-.01*np.arange(120)
    assert p_offset(x,20,100,1,.001,65)[0] is None
    x=np.where(np.arange(120)<=65,1-.04*(np.arange(120)-40),0.)
    off,reason,_=p_offset(x,40,100,1,.001,90)
    assert off is None and '20 ms' in reason


def test_unsupported_terminal_projection_does_not_move_onset_or_global_offset():
    candidates={'I':{'p':dict(pon=40,poff=72,quality=50,offset_supported=True)},
                'aVL':{'p':dict(pon=38,poff=85,quality=40,offset_supported=False,offset_reason='Sem transição terminal.')}}
    points,sources=combine_candidates(candidates,'p','pon','poff')
    assert points==dict(pon=38,poff=72)
    assert sources['poff']['rejected_candidates']=={'aVL':'Sem transição terminal.'}
    # A supported isolated terminal component must remain eligible.
    candidates['aVL']['p']['offset_supported']=True
    assert combine_candidates(candidates,'p','pon','poff')[0]['poff']==85


def test_missing_terminal_support_preserves_onset_without_inventing_duration():
    candidates={'I':{'p':dict(pon=40,poff=85,quality=40,offset_supported=False,offset_reason='Sem retorno.')}}
    assert combine_candidates(candidates,'p','pon','poff')[0]==dict(pon=40)


@pytest.mark.parametrize('qt,qrs,rr,term',[(None,80,[1.]*6,'QT indisponível'),
    (330,None,[1.]*6,'QRS indisponível'),(330,120,[1.]*6,'120 ms'),
    (330,80,[1.]*3,'mínimo de 4'),(330,80,[.59]*6,'600–1500'),
    (330,80,[1.51]*6,'600–1500'),(330,80,[.8,1.2]*5,'20,00%')])
def test_qtc_reports_actual_failed_conditions(qt,qrs,rr,term):
    assert term in ' '.join(qtc_blockers(qt,qrs,rr))


@pytest.mark.parametrize('rr',[[.6]*4,[1.5]*4,[1.]*4,[.91,1.09]*3])
def test_qtc_valid_boundary_conditions_still_pass(rr):
    assert not qtc_blockers(330,119.9,rr)


def test_qtc_gate_exactly_matches_previous_policy():
    rng=np.random.default_rng(12)
    for n in (0,3,4,30):
        for _ in range(20):
            rr=rng.uniform(.3,1.7,n)
            for qt in (None,330):
                for qrs in (None,80,120):
                    previous=qt is not None and qrs is not None and len(rr)>=4 and .6<=np.median(rr)<=1.5 and rr.std()/rr.mean()<=.1 and qrs<120
                    assert (not qtc_blockers(qt,qrs,rr))==bool(previous)


def test_qtc_rule_does_not_blame_known_sex_for_blocked_measurement():
    r,m,reps=case();m['metrics']['qtc_f'].update(value=None,reason='Variabilidade dos RR de 14,45%, acima do limite de 10%.')
    c=classify(r,m,reps);rule=next(v for v in c['rules'] if v['id']=='qt_long')
    assert rule['status']=='unavailable' and rule['reason']==m['metrics']['qtc_f']['reason']
    m['metrics']['qtc_f']['value']=400;r.meta['clinical_context']['sex']=None
    rule=next(v for v in classify(r,m,reps)['rules'] if v['id']=='qt_long')
    assert rule['reason']=='Sexo de referência não informado.'


def test_side_table_stays_above_acquisition_and_displays_unavailable_reason(tmp_path):
    app=QApplication.instance();w=window(tmp_path);r=signal_record(noise=.025);attach(w,r);a=automatic_analysis(r)
    reason='Variabilidade dos RR de 14,45%, acima do limite de 10%.'
    a['measurements']['metrics']['qtc_f'].update(value=None,reason=reason)
    w.refresh_measure_panel(a);w.resize(1080,760);app.processEvents()
    assert w.measure_table.rowCount()==6 and w.measure_table.columnCount()==2
    assert w.measure_values['qtc_f'].text()=='—' and reason in w.qtc_unavailable.text()
    assert w.qtc_unavailable.isVisible() and w.measure_table.width()<=260
    from PySide6.QtCore import QPoint
    assert w.measure_table.mapTo(w,QPoint(0,0)).x()>w.paper_scroll.mapTo(w,QPoint(0,0)).x()
    assert w.measure_table.mapTo(w,QPoint(0,w.measure_table.height())).y()<w.state_label.mapTo(w,QPoint(0,0)).y()
    w.dirty=False;w.close()
