"""Release policy for independently evaluated timing candidates.

QT/QTc are withheld because the frozen candidate failed its predeclared
record-coverage target on held-out LUDB I and II. The candidate engine is
retained for reproducible validation; app callers use this module.
"""
from .measurement_engine import (NAMES,FS,METHOD,empty,technical_quality,stable_segment,
    descriptions as _candidate_descriptions,measure_recording as _candidate_measure_recording)

QUALIFICATION={
    'I':dict(dataset='LUDB 1.0.1',held_out_subjects=160,qualified=['heart_rate','p_duration','qrs_duration'],
             qt_accepted_records=62,qt_eligible_records=160,qt_coverage=62/160),
    'II':dict(dataset='LUDB 1.0.1',held_out_subjects=160,qualified=['heart_rate','p_duration','qrs_duration'],
              qt_accepted_records=70,qt_eligible_records=159,qt_coverage=70/159),
}

def descriptions(result):
    items=_candidate_descriptions(result)
    value=result['metrics']['qrs_duration']['value']
    if value is not None:
        items[0].update(text=f"QRS em D{result['lead']}: {value:g} ms (estimativa por derivação).",
            criterion='Referência adulta: 120 ms. Não foi validada classificação por esse limiar. O erro de delineação pode ser muito maior que 3,33 ms; não é duração global nem diagnóstico de bloqueio.')
    return items

def measure_recording(recording,offset=0.,duration=None,*,lead='I',include_other=True):
    result=_candidate_measure_recording(recording,offset,duration,lead=lead,include_other=include_other)
    for item in [result]+result.get('additional_leads',[]):
        q=QUALIFICATION[item['lead']]
        item['qualification']=dict(q,qualified=list(q['qualified']),clinical_validation=False,
                                   minimum_record_coverage=.5,policy='0.7.0')
        reason=(f"QT não liberado nesta versão: cobertura de {q['qt_accepted_records']}/{q['qt_eligible_records']} "
                f"registros em D{item['lead']} na validação reservada, abaixo da meta de 50%.")
        for key in ('qt','qtc_f'):
            m=item['metrics'][key]
            m.update(value=None,status='unavailable',data_reason=m.get('reason',''),reason=reason,
                     unavailable_scope='method_qualification')
        item['metrics']['qtc_f']['formula']='QTcF = QT(ms) / RR(s)^(1/3)'
        # Do not expose candidate T endpoints as accepted QT evidence in the app.
        item['fiducials']=[{k:v for k,v in point.items() if k not in ('ton','toff')} for point in item['fiducials']]
        item['descriptions']=descriptions(item)
    return result
