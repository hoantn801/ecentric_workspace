# Copyright (c) 2026, eCentric and contributors
"""Hub: tra cap mau trang thai ve dung nghia, va ha navy DAC xuong WASH (15/09, Hoan).

Truoc dot nay nhan tinh trang cong cu tren the muon dung cap mau cua trang thai chung tu:
.badge.active = green-50/--green (ca he thong doc la "Da duyet"), .badge.coming =
navy-50/--navy ("Cho duyet"). Hau qua: mo Approval Center ra la thay mot luoi pill xanh
"trong nhu da duyet" TRUOC KHI nguoi dung gui bat cu thu gi. Day lai la trang day nguoi
dung tu vung trang thai, nen day sai o day lam hong cach doc moi man hinh phia sau.

Sau dot nay: tinh trang cong cu nam tron trong ho XAM, MOT xu ly chung cho ca ba
(migrating/coming/disabled = gray-100/gray-600, 6.87:1) - nhan chu da noi ro "Dang chuyen
doi" / "Sap ra mat" / "Da tat" roi nen sac do khong cho them thong tin nao. Ban cu cho
.badge.disabled dung gray-500 chi duoc 4.39:1, duoi nguong AA 4.5:1 cho chu nho, sua luon
trong dot nay. Trang thai Active KHONG con render nhan - "dung duoc" la mac dinh va da duoc
bao ba lan bang CTA, con tro va hover. Cap wash xanh/navy/do tra ve dung cho thu da di qua
workflow.

Kem theo la mot dot ha navy: chip dang chon va CTA tren the chuyen tu navy DAC sang navy
WASH. Chip nay gio giong het .ec-shell-item.ec-shell-active cua shell cach do 248px - truoc
day cung mot khai niem "dang chon" ma hai cach ve nguoc nhau. .retry-btn o man loi GIU navy
dac: do la hanh dong chinh duy nhat cua khung nhin do.

CHI doi CSS + mot nhanh dieu kien trong cardHtml. Khong doi API, khong doi workflow, khong
doi phan quyen, khong dung vao shell, khong dung vao 27 form con lai.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.ui.hub import page_sync

# Dau moc CHON theo kieu "khong the trung voi ban cu":
#  - chuoi CTA wash chi xuat hien sau dot nay;
#  - nhanh dieu kien bo nhan Active la thay doi JS duy nhat cua dot nay.
_LANDMARKS = (
    ".card-cta.go{ background:var(--navy-50)",
    'c.card_status==="Active" ? \'\' :',
)

# Dau moc AM: phai BIEN MAT. Neu con, live van la ban cu du sync bao thanh cong.
_MUST_BE_GONE = (
    ".badge.active{ background:var(--green-50)",
    ".chip.active{ background:var(--navy);",
)


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p189 hub sync=%s" % action, "p189 resync")
    if action == "refused":
        frappe.log_error(
            "p189: upsert TU CHOI GHI (live drift) - trang KHONG duoc cap nhat. "
            "Chay verify_approvals_baseline.ps1 roi doi chieu SUPERSEDES_SHA256.",
            "p189 REFUSED")
        return

    html = frappe.db.get_value("Web Page", {"route": "approvals"}, "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p189: trang hub thieu dau moc %s" % thieu, "p189 KHONG toi noi")
    con_sot = [m for m in _MUST_BE_GONE if m in html]
    if con_sot:
        frappe.log_error("p189: trang hub VAN con ban cu %s" % con_sot, "p189 KHONG toi noi")
