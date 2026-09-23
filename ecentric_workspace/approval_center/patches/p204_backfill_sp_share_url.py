# Copyright (c) 2026, eCentric and contributors
"""Cap bu LINK CHIA SE cho cac ban ghi SharePoint da co (23/09).

VI SAO CAN. `cap_quyen` goi createLink(scope=users) - quyen cap cho nguoi trong luong gan vao
LINK do. Nhung truoc 23/09 ham goi chi luu `da_cap` va VUT link, nen nut "Mo online" tro vao
`sp_web_url` (URL goc cua tep trong thu vien). Ai co quyen san trong thu vien thi mo duoc; nguoi
gui phieu thi khong - huong.pham bi chan tren chinh phieu cua minh (EC-CTR-2026-00019) du ten
chi nam ngay trong `sp_granted_to`.

CACH LAM - DOC KY TRUOC KHI SUA:
  * CHI goi `cap_quyen` de lay link. TUYET DOI KHONG tai tep len lai: ban tren SharePoint la ban
    SONG, nguoi duyet sua va comment truc tiep tren do. Di qua `dong_bo_phieu` la ghi de bang
    ban cua Frappe - xoa sach moi chinh sua cua ho.
  * Khong goi Graph ngay trong migrate (xem p194): chi DAT VIEC vao hang doi; worker chay sau.
  * createLink cung type + scope tra ve link DA CO, nen chay lai la an toan.

KHONG BAO GIO nem loi: patch chay trong migrate, mot exception lam chet ca lan deploy (p116).
"""
import frappe

LINK_DT = "EC SharePoint File Link"


def execute():
    try:
        if not frappe.db.exists("DocType", LINK_DT):
            return
        if not frappe.get_meta(LINK_DT).has_field("sp_share_url"):
            frappe.log_error("chua co truong sp_share_url - DocType chua dong bo?", "p204 cap bu link")
            return
        # "is not set" = rong HOAC NULL. `["in", ["", None]]` khong bat duoc NULL trong SQL -
        # cot vua them bang migrate thi moi dong deu NULL, tuc dem ra 0 va patch im lang bo qua.
        thieu = frappe.db.count(LINK_DT, {"sp_item_id": ["is", "set"],
                                          "sp_share_url": ["is", "not set"]})
        if not thieu:
            return
        frappe.enqueue(
            "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.cap_bu_link_nen",
            queue="long", timeout=1500, enqueue_after_commit=True)
        frappe.log_error("p204: da dat viec cap bu link cho %d ban ghi" % thieu, "p204 cap bu link")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p204 cap bu link - LOI (khong chan migrate)")
