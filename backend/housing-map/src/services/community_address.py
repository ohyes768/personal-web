"""Address evidence for residential admission; coordinates alone are insufficient."""
import re

MISSING_ADDRESSES = {'', '暂无', '未知', '暂无地址', '地址暂无', '未知地址', '地址未知', '无',
                     '-', '--', '—', '–', 'null', 'none', 'n/a', '未提供'}


def valid_address(value):
    return isinstance(value, str) and re.sub(r'\s+', '', value).casefold() not in MISSING_ADDRESSES


def effective_address(address, members=()):
    if valid_address(address):
        return address.strip()
    return next((r['address'].strip() for r in members if valid_address(r.get('address'))), '')
