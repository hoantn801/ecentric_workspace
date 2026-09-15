# Copyright (c) 2026, eCentric and contributors
"""De nghi thanh toan: them "Loai chi phi" (+ Brand khi can) - 09/09, Hoan.

PnL khong doc duoc chi phi vi khong o dau trong Approval Center noi mot khoan chi la chi phi
gi: Payment Request, Purchase Request, Budget Setting deu khong co truong nao nhu vay, va
`EC Approval Type.category` thi moi de nghi thanh toan deu roi vao FINANCE_BUDGET. Ket qua la
tien thue van phong va mot cai laptop len bao cao y het nhau.

Dot nay:
  * DocType `EC Loai Chi Phi` (tao truc tiep tren site 09/09) giu danh muc + hai co PnL can:
    `tinh_vao_chi_phi` (bo tick = KHONG cong vao chi phi ky do) va `can_brand`.
  * Form them DUNG MOT o chon - 27 muc gom bang <optgroup> - va o Brand chi hien voi nhung
    muc that su gan brand. Phieu thue van phong van chi thay them mot o.
  * Chong dem trung luong: phieu chi luong chon "Luong / thuong da co trong khoi luong"
    (tinh_vao_chi_phi = 0) -> PnL hien mot dong doi chieu chu khong cong lai, vi khoi luong
    da tinh khoan do tu ho so nhan su roi.

KHOA CHONG TROI: BASELINE truoc dot nay ghi sha cua RIENG ui/main_section.html trong khi trang
duoc ghi bang _html() = main + 3 panel esign, nen o vai tro luoi du phong no vo dung. Khoa van
mo duoc nho `ec_page_sync_sha:<route>` (record_live_sha ghi sau moi lan sync) - p170 da ghi
binh thuong. Dot nay dat lai BASELINE ve sha cua _html() va them sha live vao SUPERSEDES de
luoi du phong dung khi cai default bi mat.

Patch moi vi cac patch resync truoc da chay tren production.
"""
import frappe

_EXPECT = (
    'data-model="ec_loai_chi_phi"',      # o chon loai chi phi
    'expenseCatSelectHTML',              # ham dung optgroup
    'Vui lòng chọn loại chi phí.',        # chan gui khi chua chon
)


def execute():
    from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p172 payment_request sync=%s" % action, "p172 loai chi phi")
        if action == "refused":
            frappe.log_error(
                "p172: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p172 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p172: thieu landmark=%s" % (missing,), "p172 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p172 failed")
