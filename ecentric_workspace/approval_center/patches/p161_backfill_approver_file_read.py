# Copyright (c) 2026, eCentric and contributors
"""Cap bu quyen DOC tep dinh kem cho nguoi duyet cua cac phieu DANG MO (08/09, Hoan).

Truoc dot nay engine chi cap DocShare luc _activate_level ("toi luot moi duoc doc"). Nhung
`permissions.can_view_request` da cho BAT KY ai co dong approver xem toan bo noi dung phieu,
khong phan biet cap. Hai cong ap hai luat khac nhau: mo phieu trong app thi thay du gia tri
va dieu khoan, nhung bam vao TEP DINH KEM thi web server tra 403 tran (cong file cua Frappe
doc DocShare/DocPerm, khong doc luat cua app). Trieu chung 08/09: CEO khong mo duoc hop dong
cua EC-CTR-2026-00012 vi phieu moi o cap 2.

Tu nay build_snapshot cap ngay khi dung luong. Patch nay cap bu cho cac phieu DA gui truoc do
va CHUA ket thuc - de nguoi dang cho toi luot khong phai doi.

Pham vi co y HEP:
  * Chi phieu con mo (Pending / Information Required). Phieu da Approved/Rejected/Cancelled
    KHONG dong den - khong moi lai quyen tren ho so da dong.
  * Chi cap READ, dung nhom da co dong approver tren chinh phieu do - khong noi rong hon
    can_view_request.
  * `_engine_grant_read` tu bo qua neu DocShare da ton tai -> chay lai vo hai.

KHONG BAO GIO nem loi: patch chay trong migrate, mot exception lam chet ca lan deploy (p116).
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow import transitions

_OPEN = ("Pending", "Information Required")


def execute():
    granted = 0
    reqs = []
    try:
        reqs = frappe.get_all(
            "EC Approval Request", filters={"approval_status": ["in", list(_OPEN)]},
            fields=["name", "reference_doctype", "reference_name"], limit_page_length=0) or []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p161 backfill: liet ke phieu THAT BAI")
        return
    for r in reqs:
        if not r.get("reference_doctype") or not r.get("reference_name"):
            continue
        try:
            users = frappe.get_all("EC Approval Request Approver",
                                   filters={"approval_request": r["name"]}, pluck="approver") or []
            for u in dict.fromkeys(users):
                if not u or u == "Guest":
                    continue
                if frappe.db.exists("DocShare", {"share_doctype": r["reference_doctype"],
                                                 "share_name": r["reference_name"], "user": u}):
                    continue
                transitions._engine_grant_read(r["reference_doctype"], r["reference_name"], u)
                granted += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p161 backfill: %s" % r["name"])
    frappe.log_error("p161: quet %d phieu dang mo, cap bu %d quyen doc" % (len(reqs), granted),
                     "p161 backfill approver file read")
