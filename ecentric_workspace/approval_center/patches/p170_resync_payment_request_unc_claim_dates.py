# Copyright (c) 2026, eCentric and contributors
"""Resync trang De nghi thanh toan: buoc 6 khai HAI ngay luc nhan viec.

Y Hoan 09/09 sau khi nhin man hinh that:
  1. Khoi "Hoan tat - dinh kem UNC" hien ra ngay ca khi phieu con "Cho Finance nhan xu ly",
     vi no chi gac bang QUYEN (`can_complete`) chu khong gac bang TRANG THAI. Finance/SM luon
     co quyen, nen ai cung co the nhay thang qua buoc nhan viec - ma nhan viec moi la luc
     khai han xu ly.
  2. Bam "Nhan xu ly" phai hoi hai ngay KHAC NHAU: ngay thanh toan (de NHAC) va ngay co UNC
     (de tinh QUA HAN). Han xu ly tu day tinh theo ngay Finance cam ket, khong phai con so
     nguoi de nghi khai tu dau.
  3. Ke toan dinh NHAM file UNC roi da bam Hoan tat thi truoc day khong co duong nao sua tren
     man hinh. Them nut "Thay file UNC (dinh nham)" cho chinh nguoi da xu ly (hoac SM); phieu
     VAN Hoan tat, file cu duoc giu lai va danh dau "da thay".

Patch nay CHUA tung chay tren production (dot nay la lan deploy dau cua no), nen ba thay doi
tren di CHUNG mot patch. Neu no da chay roi thi phai viet patch moi - mot patch da chay se
khong bao gio chay lai, du noi dung file co doi.

KEM THEO - MOT KHOA DA LECH SAN. Truoc dot nay `page_sync.BASELINE_SHA256` ghi 6cd06565...
trong khi file trong repo la 74d10a85..., tuc khoa chong troi cua trang nay da lech tu lan
sua HTML gan nhat (quanh p161). Khoa lech thi `upsert_web_page` TU CHOI GHI, ma cac patch
resync chi log chu khong nem loi - nen trang khong cap nhat va khong ai biet. Da bump
BASELINE ve dung file dang ship va dua 74d10a85 vao SUPERSEDES.

Vi the patch nay KIEM ket qua thay vi tin: sync xong doc lai trang song, thieu dau vet moi
thi ghi mot dong Error Log noi ro - khong de no hong im lang lan nua.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

#: Dau vet cua ban MOI tren trang song.
_EXPECT = ("claim_fulfillment_unc", 'ff.status==="In Progress"', "replace_unc_attachment")
#: Dau vet cua ban CU - con lai tuc la sync khong toi noi.
_FORBID = ('Hạn xử lý (ngày thanh toán)',)


def execute():
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p170 payment_request sync=%s" % action, "p170 resync")
        if action == "refused":
            frappe.log_error(
                "p170: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat.", "p170 resync REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        left = [m for m in _FORBID if m in html]
        if missing or left:
            frappe.log_error("p170: thieu=%s con_lai=%s" % (missing, left),
                             "p170 resync KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p170 resync failed")
