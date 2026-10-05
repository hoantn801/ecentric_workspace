# Copyright (c) 2026, eCentric and contributors
"""Cap bu quyen DOC cho NGUOI XU LY cua cac phieu DANG O BUOC XU LY (05/10/2026).

linh.vuong duoc gan Role EC Data Team SAU khi EC-DTGT-2026-00035 da gui va da duyet -> khong
co DocShare cua phieu do -> bam tep dinh kem bi 403 (cong tep cua Frappe doc DocShare/DocPerm,
khong doc luat cua app). p167 (09/09) chi cap bu cho phieu con o buoc DUYET; phieu da duyet,
dang cho / dang xu ly thi khong ai cap.

Tu nay nguoi bam "Nhan xu ly" tu duoc cap (fulfillment_service._grant_read_to_claimer). Patch
nay cap bu MOT LAN cho cac phieu dang Assigned / In Progress, cho DUNG nhom nguoi xu ly da cau
hinh cua loai phieu do (configured_fulfiller_users) - khong noi rong hon can_view_request.
Phieu da Completed / Cancelled KHONG dong den. `_engine_grant_read` bo qua neu da co.
KHONG nem loi."""
import frappe

from ecentric_workspace.approval_center.shared.workflow import permissions, transitions

_ACTIVE = ["Assigned", "In Progress"]


def execute():
    granted, scanned, cache = 0, 0, {}
    for dt in transitions.FULFILLMENT_DOCTYPES:
        try:
            rows = frappe.get_all(dt, filters={"fulfillment_status": ["in", _ACTIVE]},
                                  fields=["name", "approval_request"], limit_page_length=0) or []
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p262: liet ke %s" % dt)
            continue
        for r in rows:
            scanned += 1
            try:
                atype = frappe.db.get_value("EC Approval Request", r.approval_request,
                                            "approval_type") if r.approval_request else None
                if not atype:
                    continue
                if atype not in cache:
                    cache[atype] = permissions.configured_fulfiller_users(atype)
                for u in cache[atype]:
                    if not u or u == "Guest" or frappe.db.exists(
                            "DocShare", {"share_doctype": dt, "share_name": r.name, "user": u}):
                        continue
                    transitions._engine_grant_read(dt, r.name, u)
                    granted += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), "p262: %s %s" % (dt, r.name))
    frappe.db.commit()
    frappe.log_error("p262: quet %d phieu dang xu ly, cap bu %d quyen doc" % (scanned, granted),
                     "p262 cap quyen doc nguoi xu ly")
