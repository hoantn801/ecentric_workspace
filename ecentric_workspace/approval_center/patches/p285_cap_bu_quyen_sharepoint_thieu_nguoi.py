# Copyright (c) 2026, eCentric and contributors
"""Cap bu quyen SharePoint cho tep hop dong chi moi cap cho nguoi gui (09/10/2026).

VI SAO. `_soi_guong_sharepoint` dat job KHONG doi commit: job doc phieu khi `approval_request`
chua ghi xong nen `nguoi_trong_luong` chi tra ve nguoi gui. EC-CTR-2026-00036 (huong.pham):
sp_granted_to = mot minh nguoi gui, ca 8 nguoi duyet mo "Mo online" deu bi "You need access".
Code da sua (enqueue_after_commit + tra phieu duyet theo tham chieu); patch nay va du lieu cu.

CACH LAM: CHI goi `cap_bu_link` (createLink, KHONG tai tep len lai - ban tren SharePoint la ban
song). Khong goi Graph trong migrate: chi dat viec vao hang doi (giong p204).
KHONG BAO GIO nem loi: mot exception trong migrate lam chet ca lan deploy.
"""
import frappe

LINK_DT = "EC SharePoint File Link"
JOB = "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.cap_bu_link"


def execute():
    try:
        if not frappe.db.exists("DocType", LINK_DT):
            return
        rows = frappe.get_all(LINK_DT, filters={"sp_item_id": ["is", "set"]},
                              fields=["name", "sp_granted_to"], limit_page_length=0)
        thieu = [r.name for r in rows
                 if len([e for e in (r.sp_granted_to or "").split(",") if e.strip()]) <= 1]
        for ten in thieu:
            frappe.enqueue(JOB, queue="long", timeout=300, enqueue_after_commit=True,
                           ten_ban_ghi=ten)
        if thieu:
            frappe.log_error("p285: dat viec cap bu quyen cho %d tep: %s" % (len(thieu), ", ".join(thieu)),
                             "p285 cap bu quyen SharePoint")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p285 cap bu quyen SharePoint")
