# Copyright (c) 2026, eCentric and contributors
"""Nap lai trang /sla sau khi dan nhan cho buoc xu ly va sua chu o bang Phong ban.

Doi gi: chi HTML cua trang. Khong endpoint moi, khong doi mot cong thuc nao.
Rieng nguong mau cua nhom Bao cao tuan thi doi o `constants.py` + patch p012;
trang tu doc con so moi qua `effective_dates`.

VI SAO PHAI CO SO MOI chu khong sua p010: patch CHAY MOT LAN. `bench migrate`
ghi lai nhung patch da chay va khong bao gio goi lai - nen sua noi dung p010
hom nay la sua mot tep khong ai doc nua. Moi lan doi HTML cua mot trang la mot
patch moi, khong co ngoai le.

FAIL-SAFE: moi loi bi nuot va ghi Error Log. `refused` co tieu de rieng - do la
truong hop deploy xanh ma trang van la ban cu, tuc la kieu hong duy nhat o day
khong tu noi len tieng.
"""
import frappe

TITLE_OK = "p013 nap lai trang /sla (nhan buoc xu ly)"
TITLE_REFUSED = "p013 trang /sla BI TU CHOI GHI (live da troi khoi snapshot)"


def execute():
    try:
        from ecentric_workspace.sla.pages.scoreboard import page_sync
        res = page_sync.sync()
    except Exception:
        frappe.log_error(title=TITLE_OK, message=frappe.get_traceback())
        return

    try:
        refused = isinstance(res, dict) and res.get("action") == "refused"
        frappe.log_error(title=TITLE_REFUSED if refused else TITLE_OK,
                         message=repr(res))
    except Exception:
        pass
