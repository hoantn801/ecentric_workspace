# Copyright (c) 2026, eCentric and contributors
"""Ham thuan cho ty trong: doc payload HTTP, ky truoc, so sanh, dong audit.

Payload tu HTTP luon la chuoi (rule 4.4): '{"FLD-VN":"33,5"}' phai thanh {"FLD-VN": 33.5}.
Dau phay thap phan duoc chap nhan vi nguoi dung Viet go '33,5' chu khong go '33.5'."""
import json


def _num(v):
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 0.0


def parse_weights(raw):
    data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    if not isinstance(data, dict):
        raise ValueError("weights phai la object {brand: %}")
    out = {}
    for brand, v in data.items():
        b = (brand or "").strip()
        w = _num(v)
        if b and w > 0:
            out[b] = w
    return out


def prev_period(period):
    y, m = (int(x) for x in period.split("-"))
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return "%04d-%02d" % (y, m)


def same(a, b):
    keys = set(a or {}) | set(b or {})
    return all(_num((a or {}).get(k, 0)) == _num((b or {}).get(k, 0)) for k in keys)


def diff_text(before, after):
    """Dong ghi vao nhat ky duyet: 'FLD-VN 45->50; ABBOTT moi 10; STL-VN bo (15)'."""
    parts = []
    for k in sorted(set(before or {}) | set(after or {})):
        o, n = _num((before or {}).get(k, 0)), _num((after or {}).get(k, 0))
        if o == n:
            continue
        if not o:
            parts.append("%s moi %g" % (k, n))
        elif not n:
            parts.append("%s bo (%g)" % (k, o))
        else:
            parts.append("%s %g->%g" % (k, o, n))
    return "; ".join(parts)
