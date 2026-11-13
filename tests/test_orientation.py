import copy,io
import numpy as np
import pytest
from pypdf import PdfReader
from kardiaos.orientation import evidence_state,capture_digest,DECODER_ID,normal_signs
from kardiaos.automatic_analysis import automatic_analysis,analysis_key
from kardiaos.measurements import measure_recording
from kardiaos.recording import save_recording,load_recording
from kardiaos.report import pdf_bytes
from test_measurements import signal_record
from test_automatic_analysis import fake_infer

def evidence(r,kind,channel='I',sign=1):
    ev=r.meta.setdefault('acquisition_evidence',dict(schema=1))
    item=dict(scope='capture',capture_sha256=capture_digest(r),reference_sha256='1'*64,
              reference_id='SYNTHETIC-TEST-REFERENCE',method='Simultaneous synthetic fixture comparison',reviewed_at='2026-01-01T00:00:00Z')
    if kind=='physical':item.update(status='user_declared',declared_at='2026-01-01T00:00:00Z');ev[kind]=item
    else:
        if kind=='decoder':item.update(status='reviewed_paired_reference',decoder_id=DECODER_ID,multiplier=sign)
        else:item.update(status='reviewed_amplitude_reference',mv_per_count=r.meta['mv_per_count'])
        ev.setdefault(kind,{})[channel]=item
    return item

@pytest.mark.parametrize('physical',[False,True])
@pytest.mark.parametrize('amplitude',[False,True])
@pytest.mark.parametrize('decoder',[False,True])
def test_independent_states_do_not_generate_alternative_signs(physical,amplitude,decoder):
    r=signal_record();r.meta['synthetic']=False
    if physical:evidence(r,'physical')
    for channel in ('I','II'):
        if amplitude:evidence(r,'amplitude',channel)
        if decoder:evidence(r,'decoder',channel)
    result=automatic_analysis(r,infer=fake_infer)
    assert result['mode']=='normal'
    assert len(result['scenarios'])==(3 if decoder else 0)
    assert result['evidence']['physical']==('user_declared' if physical else 'unknown')
    assert result['evidence']['amplitude']['I']==amplitude
    assert result['measurements']['metrics']['heart_rate']['value']==60
    assert all(v['raw_multipliers'] in ((1,),(1,1)) for v in result['scenarios'])

def test_channel_scope_and_derived_leads_and_amplitude_change():
    r=signal_record();r.meta['synthetic']=False;original=r.raw[:r.n].copy()
    evidence(r,'decoder','I',-1)
    result=automatic_analysis(r,infer=fake_infer)
    assert len(result['scenarios'])==1 and result['scenarios'][0]['raw_multipliers']==(-1,)
    assert normal_signs(r,'deeppsp_6l') is None
    evidence(r,'decoder','II',1);evidence(r,'amplitude','I');r.meta['mv_per_count']*=2
    assert evidence_state(r)['decoder']=={'I':-1,'II':1}
    assert not evidence_state(r)['amplitude']['I']
    calls={}
    def infer(key,values,cancel):calls[key]=values;return fake_infer(key,values,cancel)
    automatic_analysis(r,infer=infer)
    x=calls['deeppsp_6l'];np.testing.assert_allclose(x[2],x[1]-x[0]);np.testing.assert_allclose(x[3],-(x[0]+x[1])/2)
    np.testing.assert_array_equal(r.raw[:r.n],original)
    displayed=r.lead_values(300,600,raw=True)
    np.testing.assert_allclose(displayed[:,0],-original[300:600,0]*r.meta['mv_per_count'])

@pytest.mark.parametrize('change',['signal','time','decoder','reference','method','scope'])
def test_reference_cannot_transfer_to_other_signal_or_decoder(change):
    r=signal_record();r.meta['synthetic']=False;entry=evidence(r,'decoder')
    if change=='signal':r.raw[300,0]+=4
    elif change=='time':r.times[300]+=.00001
    elif change=='decoder':r.meta['decoder_id']='another-decoder'
    elif change=='reference':entry['reference_sha256']='not-a-hash'
    elif change=='method':entry['method']=''
    else:entry['scope']='all_devices'
    assert evidence_state(r)['decoder']['I'] is None

def test_legacy_metadata_roundtrip_preserves_but_does_not_validate(tmp_path):
    r=signal_record();r.meta['synthetic']=False
    r.meta.update(amplitude_verified=True,research_calibration=dict(reference='Old combined checkbox',polarity_verified=True,mv_per_count=r.meta['mv_per_count']))
    before=copy.deepcopy(r.meta['research_calibration']);p=tmp_path/'synthetic.kardia';save_recording(p,r);loaded=load_recording(p)
    state=evidence_state(loaded)
    assert state['legacy'] and state['decoder']=={'I':None,'II':None}
    assert state['amplitude']=={'I':False,'II':False} and loaded.meta['research_calibration']==before
    assert 'acquisition_evidence' not in loaded.meta
    assert not automatic_analysis(loaded,infer=fake_infer)['scenarios']

def test_technical_mode_explicit_and_never_enters_standard_print():
    r=signal_record();r.meta['synthetic']=False
    normal=automatic_analysis(r,infer=fake_infer);technical=automatic_analysis(r,infer=fake_infer,technical_mode=True)
    assert not normal['scenarios'] and len(technical['scenarios'])==10
    assert analysis_key(r)!=analysis_key(r,technical_mode=True)
    with pytest.raises(ValueError,match='tecnica'):pdf_bytes(r,layout='di',analysis=technical)
    text=PdfReader(io.BytesIO(pdf_bytes(r,layout='di',analysis=normal))).pages[0].extract_text()
    assert 'FC: 60 bpm' in text and 'Referencia por canal' in text
    assert normal['evidence']['decoder']=={'I':None,'II':None}
    assert 'I+ II-' not in text and 'I- II+' not in text

def test_timings_independent_of_declared_position_and_decoder_sign():
    r=signal_record();r.meta['synthetic']=False;a=measure_recording(r)
    evidence(r,'decoder','I',-1);evidence(r,'physical');b=measure_recording(r)
    assert a['metrics']==b['metrics']


def test_normal_interface_has_no_sign_comparison_controls(monkeypatch):
    from PySide6.QtWidgets import QApplication,QCheckBox
    from kardiaos.analysis_dialog import AutomaticAnalysisDialog
    from test_analysis_dialog import wait
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('kardiaos.analysis_dialog.automatic_analysis',lambda r,emit,cancel,**kw:automatic_analysis(r,emit,cancel,fake_infer,**kw))
    r=signal_record();dialog=AutomaticAnalysisDialog(r,autostart=False)
    dialog.start();wait(app,lambda:dialog.result is not None and not dialog.busy())
    assert dialog.score_table.rowCount()==15 and r._automatic_analysis['mode']=='normal'
    assert not dialog.findChildren(QCheckBox) and not hasattr(dialog,'technical')
    dialog.reject()


def test_physical_declaration_dialog_does_not_validate_other_states():
    from PySide6.QtWidgets import QApplication
    from kardiaos.evidence_dialog import EvidenceDialog
    app=QApplication.instance() or QApplication([])
    r=signal_record();r.meta['synthetic']=False
    dialog=EvidenceDialog(r);dialog.confirm.setChecked(True);dialog.save()
    state=evidence_state(r)
    assert state['physical']=='user_declared'
    assert state['decoder']=={'I':None,'II':None} and not any(state['amplitude'].values())

@pytest.mark.parametrize('key,channels',[('ecgfounder_1l',1),('deeppsp_2l',2),('deeppsp_6l',6)])
def test_common_positive_gain_normalization_does_not_imply_polarity(key,channels):
    from kardiaos.research_preprocess import preprocess
    t=np.arange(3000)/300
    x=np.stack([np.sin(2*np.pi*8*t+i*.1) for i in range(channels)])
    a=preprocess(x,key);b=preprocess(x*.5,key)
    np.testing.assert_allclose(a,b,atol=2e-5)
    np.testing.assert_allclose(preprocess(-x,key),-a,atol=2e-5)
