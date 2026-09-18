# Copyright (c) 2026, eCentric and contributors
"""Nap lai trang /sla sau khi dung lai toan bo giao dien theo ban dung thu da chot.

SUA MOT LOI THAT TREN BAN SONG. Thanh thanh phan o tab "Cua toi" mac dinh
opacity:0 roi doi JS bat len trong requestAnimationFrame; tren tab chua duoc
nhin, rAF bi hoan nen class khong bao gio duoc gan va thanh quan trong nhat
trang nam o opacity 0. Hoat anh gio nam han trong CSS keyframes khong fill-mode:
truoc va sau hoat anh phan tu dung style binh thuong cua no, tuc la HIEN.

Doi gi: chi HTML cua trang. Khong doi mot endpoint nao, khong doi mot con so
nao, khong doi mot bang nao. Moi lo goi API va moi hop dong du lieu giu nguyen
y ban p007 - chi cach trinh bay la khac.

VI SAO PHAI CO SO MOI chu khong sua p007: patch CHAY MOT LAN. `bench migrate`
ghi lai nhung patch da chay va khong bao gio goi lai - nen sua noi dung p007
hom nay la sua mot tep khong ai doc nua. Moi lan doi HTML cua mot trang la mot
patch moi, khong co ngoai le.

FAIL-SAFE: moi loi bi nuot va ghi Error Log. `refused` co tieu de rieng - do la
truong hop deploy xanh ma trang van la ban cu, tuc la kieu hong duy nhat o day
khong tu noi len tieng.
"""
import frappe

TITLE_OK = "p010 nap lai trang /sla (giao dien moi)"
TITLE_REFUSED = "p010 trang /sla BI TU CHOI GHI (live da troi khoi snapshot)"


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
