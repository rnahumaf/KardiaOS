"""Explicit semantic equivalences, maximum score for display, never consensus."""
from copy import deepcopy
import math

ALIASES={
    'ECGF-003':('426783006','sinus rhythm'),
    'ECGF-004':('426177001','sinus bradycardia'),
    'ECGF-005':('164889003','atrial fibrillation'),
    'ECGF-006':('427084000','sinus tachycardia'),
    'ECGF-018':('713426002','incomplete right bundle branch block'),
    'ECGF-032':('164890007','atrial flutter'),
    'ECGF-036':('445118002','left anterior fascicular block'),
}

def visible_hypotheses(merged):
    return [dict(label=r['label'],model=r['winning_model_name']) for r in merged['rows'][:3]]

def merge_hypotheses(scenarios,first,last,catalog):
    groups={};rejected=[]
    for scenario in scenarios:
        model=scenario.get('model');spec=catalog.get('models',{}).get(model)
        if not spec or scenario.get('mode')!='normal' or scenario.get('first_sample')!=first or scenario.get('last_sample_exclusive')!=last:
            rejected.append(dict(model=model,reason='unknown_model_or_different_window_mode'));continue
        if scenario.get('checkpoint_sha256')!=spec['sha256'] or not scenario.get('scores'):
            rejected.append(dict(model=model,reason='checkpoint_or_scores_unavailable'));continue
        known={z['code']:z for z in spec['labels']}
        for score in scenario['scores']:
            code=score.get('code');name=score.get('name');value=score.get('score')
            if code not in known or name!=known[code]['name'] or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
                rejected.append(dict(model=model,code=code,reason='invalid_score_or_label'));continue
            concept=(model,code);display=name
            if model in ('deeppsp_2l','deeppsp_6l'):concept=('SNOMED',code)
            if model=='ecgfounder_1l' and code in ALIASES:
                canonical,exact=ALIASES[code]
                if name.casefold()==exact:
                    concept=('SNOMED',canonical);display=exact
            source=dict(model=model,model_name=spec['name'],checkpoint_sha256=scenario['checkpoint_sha256'],
                label=deepcopy(score),first_sample=first,last_sample_exclusive=last,
                preprocessing=deepcopy(scenario.get('preprocessing')),leads=deepcopy(scenario.get('leads')),
                operational_profile=deepcopy(scenario.get('operational_profile')),source_key=scenario.get('source_key'))
            key=':'.join(concept)
            if key not in groups:groups[key]=dict(concept=key,label=display,score=float(value),winning_model=model,
                winning_model_name=spec['name'],sources=[],selection='maximum raw score for display only',calibrated_probability=False)
            entry=groups[key];entry['sources'].append(source)
            if value>entry['score']:entry.update(score=float(value),winning_model=model,winning_model_name=spec['name'])
    return dict(rows=sorted(groups.values(),key=lambda r:(-r['score'],r['concept'])),rejected=rejected,
        policy='explicit equivalence only; maximum, no averaging or consensus; differing models are uncalibrated',
        model_name_display_pending=False)
