# Copyright (c) 2026, eCentric and contributors
"""Cổng MCP cho Claude (Claude Team / Desktop / Code) - phần dính frappe.

URL để thêm connector:
    https://<site>/api/method/ecentric_workspace.claude_mcp.endpoint.handle

Đăng nhập: OAuth 2 có sẵn của Frappe v16 (OAuth Settings: bật "Enable Dynamic Client
Registration" + "Show Auth Server Metadata" + "Show Protected Resource Metadata"). Claude tự
đăng ký client, mở trang đăng nhập ERP (SSO Microsoft như bình thường), nhận token của ĐÚNG
người đó. frappe.auth.validate_oauth đặt frappe.session.user từ token TRƯỚC khi vào hàm này.

BẬT / TẮT bằng site_config (mặc định TẮT - không deploy nhầm là mở cho cả công ty):
    "ec_claude_mcp": 1                         bật cho mọi người
    "ec_claude_mcp_users": ["a@ecentric.vn"]   (tuỳ chọn) chỉ những người này - giai đoạn thử
Tắt = 404 như chưa có gì.

Vì sao allow_guest=True: chưa đăng nhập phải trả 401 + WWW-Authenticate để Claude biết đi
lấy token (RFC 9728). Để Frappe tự chặn thì nó trả 403 kèm HTML và Claude không bắt đầu OAuth.
Không có dữ liệu nào lộ ra cho Guest: mọi nhánh sau 401 đều cần user thật.
"""
import json

import frappe
from werkzeug.wrappers import Response

from ecentric_workspace.claude_mcp import protocol

VERSION = "1.0.0"


def _json(body, status=200, headers=None):
    resp = Response(json.dumps(body, ensure_ascii=False, default=str), status=status,
                    mimetype="application/json")
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def _enabled_for(user):
    conf = frappe.conf
    if not conf.get("ec_claude_mcp"):
        return False
    allow = conf.get("ec_claude_mcp_users")
    if allow:
        if isinstance(allow, str):
            allow = [x.strip() for x in allow.split(",")]
        return user in allow
    return True


def _resource_metadata_url():
    from urllib.parse import urlparse

    u = urlparse(frappe.request.url)
    return "%s://%s/.well-known/oauth-protected-resource" % (u.scheme, u.netloc)


def _clean_error(exc):
    """Lỗi một công cụ -> chữ cho Claude đọc. Rollback để thao tác dở không bị commit."""
    try:
        frappe.db.rollback()
    except Exception:
        pass
    frappe.local.message_log = []
    if isinstance(exc, frappe.PermissionError):
        msg = str(exc) or "Không có quyền."
        return "Không có quyền: " + msg
    if isinstance(exc, frappe.DoesNotExistError):
        return "Không tìm thấy: " + (str(exc) or "bản ghi không tồn tại.")
    if isinstance(exc, (frappe.ValidationError, protocol.ToolError)):
        return str(exc) or type(exc).__name__
    # lỗi bất ngờ: ghi Error Log cho dev, Claude chỉ thấy câu chung (không lộ traceback)
    frappe.log_error(frappe.get_traceback(), "Claude MCP tool error")
    return "Lỗi hệ thống khi chạy công cụ (đã ghi Error Log). Thử lại sau hoặc làm trên web."


def _audit(user, payload):
    if payload.get("method") != "tools/call":
        return
    params = payload.get("params") or {}
    frappe.logger("ec_claude_mcp", allow_site=True).info(
        {"user": user, "tool": params.get("name"), "args": list((params.get("arguments") or {}).keys())})


@frappe.whitelist(allow_guest=True, methods=["POST", "GET", "DELETE"])
def handle(**_ignored):
    """Một POST = một JSON-RPC. Bỏ qua form_dict của Frappe, đọc thân request gốc."""
    from ecentric_workspace.claude_mcp import tools

    req = frappe.request
    user = frappe.session.user
    if not frappe.conf.get("ec_claude_mcp"):
        return _json({"error": "not found"}, 404)
    if req.method != "POST":
        # Không mở luồng SSE (GET) / không có phiên để xoá (DELETE).
        return _json(protocol.error(None, protocol.INVALID_REQUEST, "Only POST is supported"), 405,
                     {"Allow": "POST"})
    if not user or user == "Guest":
        return _json(protocol.error(None, protocol.INVALID_REQUEST, "Authentication required"), 401,
                     {"WWW-Authenticate": 'Bearer resource_metadata="%s"' % _resource_metadata_url()})
    if not _enabled_for(user):
        return _json(protocol.error(None, protocol.INVALID_REQUEST,
                                    "Claude connector chưa mở cho tài khoản này."), 403)
    try:
        payload = protocol.parse(req.get_data())
    except protocol.ProtocolError as exc:
        return _json(protocol.error(None, exc.code, exc), exc.status)

    _audit(user, payload)
    server = protocol.Server(tools.TOOLS, instructions=tools.instructions() if payload["method"] == "initialize" else "",
                             version=VERSION, on_tool_error=_clean_error)
    out = server.handle(payload)
    frappe.local.message_log = []
    if out is None:
        return Response(status=202)
    return _json(out)
