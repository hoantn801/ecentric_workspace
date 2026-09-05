# Copyright (c) 2026, eCentric and contributors
"""Payment Request: go tep khi dang lap phieu + ghi ro phu luc sang SCTS the nao (05/09).

Hoan: "them cho de xoa nua chu, khong co cho xoa thi sao xoa duoc file khong dung?". Khoi
"Tai lieu & Ky so" chi co nut Go trong cua so "Can bo sung"; luc dang soan - luc tai nham
nhieu nhat - khong co nut nao.

- document_signing_section.html: nut "Go" cho MOI tep khi dang lap phieu (editable +
  can_classify) -> esign.api.remove_attachment (POST; go ca dong goi ky + vi tri ky; hoi
  truoc neu da dat o ky). Dong bo chung tu ghi "chi luu tren ERP, khong gui SCTS" (Excel,
  Word) hoac "gui SCTS dang PDF" (anh).
- main_section.html: khung "Dinh kem" ve lai khi khoi ky so bao vua go tep.

Patch moi vi p139 (payment_request) da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ('data-remove-any="1"', 'payr:attachments-changed')


def execute():
    res = page_sync.sync()
    frappe.log_error("p144 payment_request sync=%s" % (res or {}).get("action"), "p144 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p144: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
