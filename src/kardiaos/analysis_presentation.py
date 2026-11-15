"""Presentation of incomplete criteria without changing their rule status."""


def criterion_group(rule):
    if rule['status'] == 'detected':
        return 'detected'
    if (rule['status'] == 'unavailable' or rule.get('technical_status') == 'indeterminate'
            or any(rule.get(key) for key in ('possible', 'possible_context', 'possible_morphology_leads'))):
        return 'review'
    return 'not_detected'


def pending_messages(classification, compact=False):
    groups = {}
    labels = set()
    for rule in classification.get('rules', []):
        if rule['status'] != 'unavailable':
            continue
        labels.add(rule['label'])
        reason = rule.get('reason') or 'Dados necessários indisponíveis.'
        groups.setdefault(reason, []).append(rule['label'])
    messages = []
    for reason, names in groups.items():
        detail = f'{len(names)} critérios não avaliados' if compact and len(names) > 2 else 'Não avaliados: ' + '; '.join(names)
        messages.append(reason.rstrip('.') + '. ' + detail + '.')
    messages.extend(item for item in classification.get('missing', []) if item not in labels)
    return messages


def descriptive_messages(classification):
    morphology, possibilities, limitations = [], [], []
    for rule in classification.get('rules', []):
        if rule.get('presentation') == 'description':
            if rule['status'] == 'detected':
                morphology.append(rule['label']+' — '+', '.join(rule['leads'])+'.')
            if rule.get('possible_morphology_leads'):
                morphology.append('Possível '+rule['label']+' — '+', '.join(rule['possible_morphology_leads'])+'; componente discreto na mediana completa.')
        if rule.get('possible'):
            p=rule['possible']
            text='Possível '+rule['label']+(' — '+', '.join(p['leads']) if p['leads'] else '')+'; '+', '.join(p['subsets'])+'.'
            (morphology if rule.get('presentation')=='description' else possibilities).append(text)
        limitations.extend(rule.get('limitations', []))
        if rule.get('possible_context'):possibilities.append(rule['possible_context'])
    limitations.extend(classification.get('sinus_limitations',[]))
    return morphology,possibilities,list(dict.fromkeys(limitations))
