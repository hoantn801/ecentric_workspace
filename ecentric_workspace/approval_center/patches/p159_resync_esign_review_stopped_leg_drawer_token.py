# Copyright (c) 2026, eCentric and contributors
"""Ra soat SCTS dem 08/09 - phan giao dien (payment-request + ec-esign/ops).

Trang approvals/payment-request (page_sync ghep main_section + panel nguoi de nghi + khoi
"Tai lieu & ky so"):
  * main_section: chan ky da DUNG cua chinh nguoi duyet (signing_readiness.stopped) - chua gui
    thi van co "Duyet & Ky" + ghi chu; co the da gui thi khong moi bam (truoc: bam = 500).
  * requester_signing_panel: vong doi 6 phut khong bi dat lai moi 10 giay; Failed -> "Gui &
    ky lai"; Reconciliation Required -> "Dang doi soat" (truoc: ca hai deu doc "da gui chu ky").
  * document_signing_section: openDrawer co ma phien (stale) cho moi phan hoi - mo tep X cham
    roi mo tep Y khong con hien trang cua X duoi ten Y; DRW.signed reset khi doi phieu; bang
    loi tai duoc go khi tai lai thanh cong; van ban chi-xem theo ly do; tai tep khoa nut khi
    dang tai + ly do 413.
  * main_section: doi phieu (popstate/go) thi xoa state.unc - UNC cua phieu A khong gan vao B.
  * payment_request_signing (bang cu, khong ve): boot khong goi get_signing_status /
    signing_readiness nua (3 lan/luot xem phieu -> 1).
Trang ec-esign/ops: {queued:true} (Thu lai / Gui lai co kiem) bao "Xong" thay vi do.
Patch moi vi p158 da chay (patch chay MOT LAN). Tu VERIFY landmark tren ca hai trang.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
from ecentric_workspace.platform.esign import ops_page_sync

_PR_LANDMARKS = ("state._signReady.stopped", "var myTok = DRW.docToken",
                 "function _roText(st)", "WAIT.expired", "function _uploadReason(",
                 "if(prev!==state.id) state.unc={};",
                 'if(!this.RENDER_LEGACY_UI){ panel.innerHTML = ""; return Promise.resolve(); }')
_OPS_LANDMARKS = ("|| o.queued",)


def execute():
    res = page_sync.sync()
    frappe.log_error("p159 payment_request sync=%s" % (res or {}).get("action"), "p159 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _PR_LANDMARKS if m not in html]
    if missing:
        raise Exception("p159: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
    res2 = ops_page_sync.sync()
    frappe.log_error("p159 ops sync=%s" % (res2 or {}).get("action"), "p159 resync")
    ops = frappe.db.get_value("Web Page", {"route": ops_page_sync.ROUTE}, "main_section_html") or ""
    missing = [m for m in _OPS_LANDMARKS if m not in ops]
    if missing:
        raise Exception("p159: trang %s thieu %s sau sync" % (ops_page_sync.ROUTE, missing))
