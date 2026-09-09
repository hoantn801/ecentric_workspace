# Copyright (c) 2026, eCentric and contributors
"""Form Tuyen dung: tep da tai len phai NHIN THAY duoc (09/09, Hoan bao).

Tai xong chi hien mot toast roi tat. Du lieu co luu that (`request_attachment` vao state, van
gui kem phieu) nhung o nhap KHONG duoc ve lai sau khi tai, con `renderSummary()` thi khong he
co dong nao cho tep dinh kem -> man hinh khong con dau vet nao, nguoi dung tuong tai hong.

Sua: o nhap co san mot cho co dinh (`#hire-file-name`) de ghi TEN TEP ngay sau khi tai, va
Tom tat them dong "Tep dinh kem". Hien ten tep chu khong hien ca duong dan
(/private/files/HD%20090926_... doc khong ra gi) - co giai ma %20.

Chi rieng form Tuyen dung dung duong nay; cac form khac khong dinh.
Patch moi vi cac patch resync truoc da chay tren production. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.hiring_request.infrastructure import page_sync

_LANDMARKS = ('id="hire-file-name"', "function showFileName(", "function fileLabel(")


def execute():
    res = page_sync.sync()
    frappe.log_error("p167 hiring_request sync=%s" % (res or {}).get("action"), "p167 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/hiring-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p167: trang approvals/hiring-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
