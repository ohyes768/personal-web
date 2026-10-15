"""TMSF second-hand listing admission gate; unknown counts are never zero."""
from src.services.tmsf_property_type import effective_market_state

MIN_LISTINGS = 3


def listing_gate(records, master=None):
    relevant = [r for r in records if r.get('source') == 'tmsf' and effective_market_state(r) != 'new_house'
                and (effective_market_state(r) == 'second_hand' or 'listing_count' in r
                     or r.get('listing_count_checked_at') or (master and 'listing_count' in master))]
    if not relevant:
        return None, ''
    counts = []
    unknown = False
    for record in relevant:
        value = record.get('listing_count')
        if 'listing_count' not in record and master and len(relevant) == 1 and not record.get('listing_count_checked_at'):
            value = master.get('listing_count')
        if record.get('listing_count_error') or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            unknown = True
        else:
            counts.append(value)
    # A low count on one phase must not exclude another phase with sufficient listings.
    if any(n >= MIN_LISTINGS for n in counts):
        return None, ''
    if unknown or not counts:
        return 'pending', '二手房挂牌数量缺失或获取失败，待确认'
    return 'excluded', f'透明售房网二手房挂牌 {max(counts)} 套，少于 {MIN_LISTINGS} 套，不收录'
