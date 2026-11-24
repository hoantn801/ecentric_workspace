# Copyright (c) 2026, eCentric and contributors
"""Doi thoi gian giua may studio (epoch ms hoac ISO) va ERP (Datetime gio VN, khong mui gio).

Dat o host_qc/utils/ thay cho common/utils/date.py: chua co module thu hai dung (frappe-rules muc 7)."""
import datetime as _dt
from zoneinfo import ZoneInfo

from ecentric_workspace.host_qc.constants.rules import TZ

VN = ZoneInfo(TZ)


def to_dt(value):
    """epoch ms / epoch giay / chuoi ISO (co hoac khong mui gio) -> datetime naive gio VN. Sai -> None."""
    if value in (None, ""):
        return None
    if isinstance(value, _dt.datetime):
        return value.astimezone(VN).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().lstrip("-").isdigit()):
        n = float(value)
        if n > 1e11:                      # mili giay
            n = n / 1000.0
        return _dt.datetime.fromtimestamp(n, VN).replace(tzinfo=None)
    try:
        d = _dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(VN).replace(tzinfo=None) if d.tzinfo else d


def to_ms(d):
    """datetime naive gio VN -> epoch ms."""
    if not d:
        return None
    if isinstance(d, str):
        d = to_dt(d)
    return int(d.replace(tzinfo=VN).timestamp() * 1000)


def iso(d):
    """datetime naive gio VN -> ISO co +07:00 (dang SessionConfig cua app)."""
    if not d:
        return None
    if isinstance(d, str):
        d = to_dt(d)
    return d.replace(tzinfo=VN).isoformat(timespec="seconds")


def rel(ms):
    """Mili giay tinh tu dau phien -> hh:mm:ss (giong fmtRel cua app)."""
    s = max(0, int((float(ms or 0)) // 1000))
    return "%02d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)


def now():
    """Gio hien tai (gio VN, naive) - giong Datetime ERP luu."""
    return _dt.datetime.now(VN).replace(tzinfo=None)
