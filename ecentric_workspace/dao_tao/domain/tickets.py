# Copyright (c) 2026, eCentric and contributors
"""Ve tuan: toi da 3 ve / nguoi / tuan, tinh CHUNG ve tu quiz + bai thuc hanh + quiz bai hoc.
Tuan = thu Hai -> Chu nhat. Thuan Python."""
import datetime

from ecentric_workspace.dao_tao import constants as C


def week_start(d):
    if isinstance(d, datetime.datetime):
        d = d.date()
    return d - datetime.timedelta(days=d.weekday())


def grant(already, want, cap=C.TICKETS_PER_WEEK):
    """-> so ve DUOC cap them (khong vuot tran tuan)."""
    return max(0, min(int(want or 0), cap - int(already or 0)))


def week_label(d):
    ws = week_start(d)
    return "Tuần %02d · %s" % (ws.isocalendar()[1], ws.strftime("%d/%m"))
