# Copyright (c) 2026, eCentric and contributors
"""Cap bu quyen DOC cho NGUOI XU LY cua cac phieu DANG MO (09/09, chi Dan hoi).

p163 (08/09) cap bu cho nguoi DUYET, va ghi rang nhom duoc cap "dung bang nhom ma
can_view_request da cho xem". Cau do bo sot mot nhom: `can_view_request` con cho Fulfiller
DUOC CAU HINH xem (chi Dan - Role EC Finance - la Fulfiller cua PAYMENT_REQUEST), nhung ho
khong duoc cap gi cho toi khi buoc xu ly kich hoat.

Trieu chung 09/09: chi Dan mo EC-PAYR-2026-00073 (dang o buoc 1-2) thi Frappe nem
"Not permitted" - vi `query_service.detail` goi `frappe.get_doc` TRUOC khi hoi luat cua app -
va bam vao tep dinh kem thi web server tra 403. Dung nguyen lop loi 08/09, khac vai dien.

Tu nay `grant_read_to_snapshot_approvers` cap ngay luc dung luong. Patch nay cap bu cho cac
phieu DA gui truoc do va CHUA ket thuc.

Pham vi co y HEP, giong p163:
  * Chi phieu con mo (Pending / Information Required). Phieu da Approved/Rejected/Cancelled
    KHONG dong den - khong moi lai quyen tren ho so da dong.
  * Chi cap READ, dung nhom Fulfiller duoc cau hinh cua chinh loai phieu do - khong noi
    rong hon can_view_request.
  * `_engine_grant_read` tu bo qua neu DocShare da ton tai -> chay lai vo hai.

KHONG BAO GIO nem loi: patch chay trong migrate, mot exception lam chet ca lan deploy (p116).
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow import permissions, transitions

_OPEN = ("Pending", "Information Required")


def execute():
    granted = 0
    reqs = []
    try:
        reqs = frappe.get_all(
            "EC Approval Request", filters={"approval_status": ["in", list(_OPEN)]},
            fields=["name", "reference_doctype", "reference_name", "approval_type"],
            limit_page_length=0) or []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p167 backfill: liet ke phieu THAT BAI")
        return
    # Mot loai phieu hoi MOT lan: cau hinh khong doi giua cac phieu cung loai, va mot lan
    # migrate co the quet hang tram phieu.
    cache = {}
    for r in reqs:
        if not r.get("reference_doctype") or not r.get("reference_name"):
            continue
        atype = r.get("approval_type")
        if not atype:
            continue
        try:
            if atype not in cache:
                cache[atype] = permissions.configured_fulfiller_users(atype)
            for u in cache[atype]:
                if not u or u == "Guest":
                    continue
                if frappe.db.exists("DocShare", {"share_doctype": r["reference_doctype"],
                                                 "share_name": r["reference_name"], "user": u}):
                    continue
                transitions._engine_grant_read(r["reference_doctype"], r["reference_name"], u)
                granted += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p167 backfill: %s" % r["name"])
    frappe.log_error("p167: quet %d phieu dang mo, %d loai, cap bu %d quyen doc"
                     % (len(reqs), len(cache), granted),
                     "p167 backfill fulfiller file read")
