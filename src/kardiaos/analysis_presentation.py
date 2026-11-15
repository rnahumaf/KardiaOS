"""Presentation of incomplete criteria without changing their rule status."""


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
