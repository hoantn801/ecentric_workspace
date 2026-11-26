# Copyright (c) 2026, eCentric and contributors
"""Tac vu nen Cong cu dung chung (hooks.py scheduler_events).

  * Moi phut: don hang doi (het gio / de yen / khong mo kip -> nguoi tiep theo) + keo file xuat.
    Trang dang mo cung tu don moi 10 s; job lo khi khong ai mo trang.
  * 03:20 hang ngay: xoa file xuat qua 7 ngay.
Idempotent; loi mot cong cu khong chan cong cu khac.
"""
import frappe

from ecentric_workspace.shared_tools import constants as C
from ecentric_workspace.shared_tools import exports as X
from ecentric_workspace.shared_tools import service as S

TOOLS = (C.TOOL_KALODATA,)


def every_minute():
    for key in TOOLS:
        try:
            host = S.host_state(key, force=True)
            S.tick(key, host=host)
            X.sync(key, host=host)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="shared_tools every_minute %s" % key)


def purge_exports():
    try:
        frappe.logger("shared_tools").info("purge exports: %s" % X.purge())
    except Exception:
        frappe.log_error(title="shared_tools purge_exports")
