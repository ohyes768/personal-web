"""Pure current-fact outcomes, distinct from admission and transport diagnostics."""


def collection_resolution(record):
    error = record.get('collection_error_code') or ''
    message = str(record.get('property_type_error') or '')
    if error in {'identity_mismatch', 'invalid_target'} or 'identity_mismatch' in message:
        return dict(state='identity_conflict', retryable=False)
    if error == 'missing_facts':
        return dict(state='facts_pending', retryable=False)
    if any(record.get(k) for k in ('property_type_error', 'listing_count_error', 'market_state_error')):
        return dict(state='retryable', retryable=True)
    from src.services.residential_classifier import NON_RESIDENTIAL_TYPES
    if record.get('property_type') in NON_RESIDENTIAL_TYPES:
        return dict(state='non_residential', retryable=False)
    if record.get('address_error') and record.get('source_kind', 'community') != 'project' and record.get('market_state') != 'new_house':
        return dict(state='retryable', retryable=True)
    if not record.get('property_type'):
        return dict(state='facts_pending', retryable=False)
    if record.get('address_pending') or record.get('address_error'):
        if record.get('source_kind', 'community') == 'project' or record.get('market_state') == 'new_house':
            return dict(state='position_pending', retryable=False)
        return dict(state='retryable', retryable=True)
    return dict(state='ready', retryable=False)
