# Copyright (c) 2026, eCentric and contributors
"""Quyet dinh canh bao - logic thuan, test duoc khong can bench."""

import re

_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def valid_ip(ip):
    return bool(ip) and bool(_IP.match(ip.strip()))


def classify(http_code):
    """Ma HTTP cua lan goi thu boxme -> ok | auth_fail | down."""
    if http_code == 200:
        return "ok"
    if http_code in (401, 403):
        return "auth_fail"
    return "down"


def decide(prev_ip, prev_status, ip, status):
    """Tra ve danh sach canh bao [(kind, dedupe_suffix)].

    - IP doi (va do duoc IP hop le) -> 'ip_changed' (1 lan cho moi IP moi).
    - boxme 401/403 -> 'auth_fail' (1 lan/ngay/IP - goi ben ngoai them ngay vao dedupe).
    - boxme tu loi sang ok -> 'recovered' (1 lan cho moi IP).
    - 'down' (timeout/5xx) khong bao: thuong thoang qua, sync da co log rieng.
    """
    out = []
    if valid_ip(ip) and valid_ip(prev_ip) and ip != prev_ip:
        out.append(("ip_changed", ip))
    if status == "auth_fail":
        out.append(("auth_fail", ip or "?"))
    elif status == "ok" and prev_status == "auth_fail":
        out.append(("recovered", ip or "?"))
    return out


def message(kind, prev_ip, ip, http_code, boxme_user):
    """(tiêu đề, nội dung) cho thông báo - tiếng Việt có dấu."""
    if kind == "ip_changed":
        return ("GBS: IP server ERP vừa đổi - cần gửi GBS whitelist",
                "IP gọi ra của team.ecentric.vn đổi từ %s sang %s (Frappe Cloud có thể vừa chuyển server). "
                "Gửi GBS IP mới để whitelist cho tài khoản %s, nếu không đồng bộ SO/PO sẽ bị chặn."
                % (prev_ip, ip, boxme_user or "tích hợp"))
    if kind == "auth_fail":
        return ("GBS đang CHẶN kết nối từ ERP (HTTP %s)" % http_code,
                "Gọi thử boxme bằng khoá tích hợp bị từ chối (HTTP %s). IP gọi ra hiện tại: %s. "
                "Kiểm tra GBS đã whitelist IP này chưa, hoặc khoá API trong GBS Settings còn đúng không. "
                "Trong lúc này phiếu duyệt xong ở EC KHÔNG sang được GBS." % (http_code, ip or "không đo được"))
    return ("GBS: kết nối từ ERP đã hoạt động lại",
            "Gọi thử boxme đã thành công lại (IP %s). Phiếu bị lỡ trong lúc chặn có thể cần bấm Check Status hoặc gửi lại."
            % (ip or "?"))
