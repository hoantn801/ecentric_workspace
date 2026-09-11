# Copyright (c) 2026, eCentric and contributors
"""AI Topup: bao DUNG cau khi (AI tool, email) da co tai khoan - 11/09, Hoan.

Trieu chung: bam "Gui phe duyet" khong len duoc, man hinh chi noi "Da co loi khi luu/gui
yeu cau. Vui long thu lai".

DO TREN PRODUCTION truoc khi sua (khong suy doan): hai phieu NHAP cua hon.nguyen
(EC-AITOP-2026-00020 16:51, -00021 17:07) nam trong DB voi approval_request = NULL. Tuc
`save_draft` CHAY DUOC, chi `submit_request` bi chan. Chan la DUNG: ca hai chon "Tai khoan
moi" cho cap (Heygen, ai@ecentric.vn) ma cap do da co - EC-AIACC-00005, dang Active.

Cai sai nam o MAN HINH: `applyBackendError` khong co nhanh nao khop cau server nem ra, nen
roi xuong `friendlyErr` va hien mot loi khuyen KHONG BAO GIO dung - "thu lai" thi van chan.
Sua: bat cau do, to do o "Hinh thuc tai khoan", hien NGUYEN VAN cau cua server. Kem theo
them account_mode vao danh sach showFieldErrors quet (khong co thi to do xong khong hien).

Landmark = dieu PHAI CO tren ban song."""
import frappe

from ecentric_workspace.approval_center.features.ai_topup.infrastructure import page_sync

_LANDMARKS = ('"account_mode"', "already exists")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p180 ai_topup sync=%s" % action, "p180 resync")
    if action == "refused":
        frappe.log_error(
            "p180: upsert TU CHOI GHI (khoa chong troi). Trang KHONG duoc cap nhat - doc "
            "live_sha trong ket qua roi them vao SUPERSEDES_SHA256.", "p180 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/ai-topup"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        # Khong nem loi: mot exception o day lam chet CA LAN MIGRATE (bai hoc p116).
        frappe.log_error("p180: trang ai-topup thieu dau moc %s" % thieu, "p180 KHONG toi noi")
