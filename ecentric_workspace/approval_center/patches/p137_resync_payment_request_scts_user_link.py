# Copyright (c) 2026, eCentric and contributors
"""Panel nguoi de nghi: khoi "Ket noi tai khoan ky so SCTS".

04/09/2026. eContract giao buoc Trinh ky cho tai khoan TAO chung tu va chi ky bang chung thu
cua nguoi giu task. ERP tao moi chung tu bang mot tai khoan tich hop, nen nguoi de nghi
khac tai khoan do khong bao gio ky duoc buoc dau (00046/00047/00048/00050 - thu 6 cach, ke
ca gan vai tro cho node va gui signatureInfo cua ho: chu ky dong len van la cua tai khoan
tich hop).

Duong dung: chung tu phai do CHINH nguoi de nghi tao. Nguoi dung nhap mat khau SCTS mot lan
trong panel nay; ERP giu TOKEN (1 nam) tren EC SCTS User Mapping, khong luu mat khau. Chan
nguoi de nghi tao chung tu + Trinh ky bang token do (platform/esign/user_link.py). Chua ket
noi thi bi chan ngay luc bam Gui, khong tao chung tu rac.

Patch nay chi dong bo lai trang Payment Request de panel moi len. Truong moi cua DocType
di theo migrate binh thuong. Patch moi vi p136 da chay - patch chay MOT LAN.

Tu VERIFY: doc lai trang tu DB va nem neu khoi ket noi chua co - khong "chay xong ma khong
doi gi" (bai hoc p134).
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARK = 'id="ecReqLinkForm"'


def execute():
    res = page_sync.sync()
    frappe.log_error("p137 payment_request sync=%s" % (res or {}).get("action"),
                     "p137 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p137: trang approvals/payment-request van chua co khoi ket noi "
                        "SCTS sau sync (action=%s)" % (res or {}).get("action"))
