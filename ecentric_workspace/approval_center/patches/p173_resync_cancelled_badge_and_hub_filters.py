# Copyright (c) 2026, eCentric and contributors
"""Resync HAI trang: phieu da huy danh dau do + hang filter hub thang hang - 10/09, Hoan.

  1. De nghi thanh toan (/approvals/payment-request). EC-PAYR-2026-00047 da huy nhung badge
     van mau xam va cap 2 van hien "Dang xu ly" mau navy - nhin y het mot phieu dang chay.
     Goc: `buildStepper` chua bao gio doc `approval_status`; no chi nhin `level_status` va
     `current_level`, ma huy phieu KHONG doi hai thu do.

  2. Hub (/approvals/all-requests). Hang filter trong "lon xon nhu vo hai dong". Da do tren
     prod: grid KHONG xuong dong - 8 cot tren mot hang. Cai lech la NHAN, chenh 10px, vi hai
     thanh phan dung chung cua site cao hon o nhap thuong: `.ec-dp-wrap` (o lich) 40px va
     `.ec-cb` (o Trang thai) 39px so voi 30px; `.fgrid` lai `align-items:end` nen o nao cao
     hon se day nhan cua no len. Chua bang cach ep chieu cao ve 28px TRONG PHAM VI `.fgrid`
     (khong sua bundle dung chung), doi sang `align-items:start`, va giam 1-2 co chu.

MOT PATCH cho HAI trang: hai trang deu chi can goi `page_sync.sync()`, tach doi thanh hai
file khong them dam bao gi. Tien le: p118 resync 27 form trong mot patch.

Trang hub KHONG co khoa chong troi (`sync()` cua no khong truyen `expect_sha`), nen chi
trang thanh toan moi co the tra ve "refused".
"""
import frappe

#: Dau vet ban MOI tren tung trang song.
_EXPECT = {
    "approvals/payment-request": ("markCancelled", "is-cancelled",
                                  '"Cancelled":["b-red","Đã hủy"]'),
    "approvals/all-requests": (".fgrid .ec-dp-wrap", "align-items:start"),
}
#: Dau vet ban CU - con lai tuc la sync khong toi noi.
_FORBID = {
    "approvals/payment-request": ('"Cancelled":["b-gray","Đã hủy"]',),
    "approvals/all-requests": ("font-size:14px; font-weight:600; color:var(--gray-500); cursor:pointer;",),
}


def _sync_one(route, mod):
    res = mod.sync()
    action = (res or {}).get("action")
    frappe.log_error("p173 %s sync=%s" % (route, action), "p173 resync")
    if action == "refused":
        frappe.log_error(
            "p173 %s: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
            "trong BASELINE/SUPERSEDES va cung khong khop ec_page_sync_sha - trang KHONG "
            "duoc cap nhat. Doc live_sha trong ket qua roi them vao SUPERSEDES_SHA256."
            % route, "p173 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
    missing = [m for m in _EXPECT.get(route, ()) if m not in html]
    left = [m for m in _FORBID.get(route, ()) if m in html]
    if missing or left:
        frappe.log_error("p173 %s: thieu=%s con_lai=%s" % (route, missing, left),
                         "p173 KHONG toi noi")


def execute():
    from ecentric_workspace.approval_center.features.payment_request.infrastructure \
        import page_sync as pr_sync
    from ecentric_workspace.approval_center.ui.all_requests import page_sync as hub_sync
    for route, mod in (("approvals/payment-request", pr_sync),
                       ("approvals/all-requests", hub_sync)):
        try:
            _sync_one(route, mod)
        except Exception:
            # Mot trang hong khong duoc keo theo trang kia, va khong duoc lam chet ca lan
            # migrate (bai hoc p116).
            frappe.log_error(frappe.get_traceback(), "p173 resync failed %s" % route)
