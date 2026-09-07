# Copyright (c) 2026, eCentric and contributors
"""Hub "Tat ca yeu cau": o ly do tu choi/bo sung khong con dinh sang ho so ke (07/09, Hoan).

Khung popup dung MOT LAN (ensureShell) nen `#apl-note` song qua cac lan bam < >: go ly do cho
A, sang B van thay o do voi chu cua A; "Xac nhan" van tu choi A (dung) nhung nguoi dung nhin
tuong tu choi B. Gio moi lan do ho so moi (drawDetail / showLoading / nhanh loi) goi
resetNote(): dong o, xoa chu, tra lai hang nut.
Cung chuyen: nut "Huy" tren dai "Nhap cua toi" (nhap khong dung thi thanh rac) -> POST
reporting.actions.discard_draft, cung duong facade.cancel voi nut tren form.
Patch moi vi p143 da chay tren production. Tu VERIFY ca hai landmark.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("function resetNote(box)", "function discardDraft(btn)")


def execute():
    res = page_sync.sync()
    frappe.log_error("p148 all_requests sync=%s" % (res or {}).get("action"), "p148 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p148: hub thieu %s sau sync (action=%s)"
                        % (", ".join(missing), (res or {}).get("action")))
