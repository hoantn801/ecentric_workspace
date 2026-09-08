# Copyright (c) 2026, eCentric and contributors
"""Sua loi that o nut "Chuyen nguoi xu ly": goi ham khong ton tai (08/09).

`doReassign` (p152) goi `applyDetail(r)` sau khi chuyen viec thanh cong. Nhung trong nam form
thi asset_request / data_request / document_request KHONG co ham do - chung dung
`refreshDetail`. Ket qua tren ba form ay: server chuyen viec XONG XUOI, roi trinh duyet nem
ReferenceError, va chinh `.catch` cua chuoi promise nuot no lai thanh mot toast BAO LOI ->
nguoi dung tuong that bai va bam lai.

Bai hoc: nam form nay giong nhau 90%, khong phai 100%. Chep mot doan JS sang ca nam ma khong
kiem tung ten ham co that trong tung file la du de sinh loi kieu nay. Da them test doc than
`doReassign`/`doClaim` va doi chieu TUNG lenh goi voi cac ham thuc su dinh nghia trong file
(co boc chu thich + chuoi ky tu truoc khi quet, neu khong thi chinh cau chu thich
"Ba form (asset/...)" cung khop mau "ten(").

Cung dot: engine bao them cho CHU CU khi viec bi chuyen di (truoc chi bao nguoi de nghi va
chu moi, nen nguoi bi lay viec khong he biet).

Patch moi vi p152 da chay tren production. Tu VERIFY landmark tung trang.
"""
import frappe

_PAGES = (
    ("asset_request", "approvals/asset-request"),
    ("data_request", "approvals/data-request"),
    ("document_request", "approvals/document-request"),
    ("resignation", "approvals/resignation"),
    ("system_request", "approvals/system-request"),
)
_LANDMARKS = ('if(typeof applyDetail==="function") applyDetail(r); else refreshDetail();',)


def execute():
    missing_all = []
    for feature, route in _PAGES:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
        res = mod.sync()
        frappe.log_error("p160 %s sync=%s" % (feature, (res or {}).get("action")), "p160 resync")
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        missing = [m for m in _LANDMARKS if m not in html]
        if missing:
            missing_all.append("%s (action=%s)" % (route, (res or {}).get("action")))
    if missing_all:
        raise Exception("p160: chua nhan ban moi: " + " | ".join(missing_all))
