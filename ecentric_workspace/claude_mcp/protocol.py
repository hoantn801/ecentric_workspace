# Copyright (c) 2026, eCentric and contributors
"""MCP (Model Context Protocol) - phần giao thức THUẦN, không import frappe.

Vì sao tự viết thay vì dùng MCP có sẵn của Frappe v16 (`/api/v2/mcp`):
  * MCP có sẵn trả 403 cho mọi tài khoản không phải System User ("only available to desk users"),
    mà ~44% tài khoản eCentric là Website User (xem action_center/resolvers.py). Họ cũng dùng
    Claude Team, nên cần một cổng mở cho cả hai loại tài khoản.
  * Bộ công cụ có sẵn là list_documents / call_method chung chung: Claude phải tự đoán DocType,
    bỏ qua thứ tự "Việc cần làm" (pm/api/queue.py) và luật quyền riêng của từng màn.
    Ở đây mỗi công cụ gọi ĐÚNG hàm mà màn hình đang gọi, nên quyền, thứ tự, thông báo và audit
    giữ nguyên như khi bấm trên web.

Kiểu vận chuyển: Streamable HTTP, KHÔNG giữ phiên (stateless), mỗi POST một JSON-RPC, trả JSON
(không SSE). Đủ cho tools; Claude.ai / Claude Desktop / Claude Code đều chấp nhận.

File này chỉ biết JSON-RPC. Phần frappe (đăng nhập, Response, rollback) nằm ở endpoint.py,
phần nghiệp vụ ở tools.py. Tách vậy để test chạy được không cần bench.
"""
import json

#: Các bản giao thức đã kiểm. Bản đầu = bản trả lời khi client hỏi bản lạ.
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_VERSION = SUPPORTED_VERSIONS[0]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

SERVER_NAME = "ecentric-erp"


class ProtocolError(Exception):
    """Lỗi giao thức (không phải lỗi của một công cụ)."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status


class ToolError(Exception):
    """Lỗi nghiệp vụ có chủ đích, trả về cho Claude đọc (isError=true), không phải HTTP lỗi."""


def negotiate(requested):
    return requested if requested in SUPPORTED_VERSIONS else DEFAULT_VERSION


def parse(body):
    """bytes/str -> dict một request. Ném ProtocolError nếu sai khuôn."""
    try:
        payload = json.loads(body or b"")
    except (ValueError, UnicodeDecodeError):
        raise ProtocolError(PARSE_ERROR, "Body is not valid JSON") from None
    if isinstance(payload, list):
        # Bản 2025-06-18 trở đi bỏ batch. Không hỗ trợ cho gọn.
        raise ProtocolError(INVALID_REQUEST, "JSON-RPC batching is not supported")
    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0"
            or not isinstance(payload.get("method"), str)
            or not isinstance(payload.get("params", {}), dict)):
        raise ProtocolError(INVALID_REQUEST, "Body must be one JSON-RPC 2.0 request or notification")
    if "id" in payload and (isinstance(payload["id"], bool)
                            or not isinstance(payload["id"], (str, int))):
        raise ProtocolError(INVALID_REQUEST, "Request id must be a string or integer")
    return payload


def result(req_id, res):
    return {"jsonrpc": "2.0", "id": req_id, "result": res}


def error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": str(message)}}


def tool_result(data, is_error=False):
    """Kết quả một công cụ: text JSON (mọi client đọc được) + structuredContent (client mới)."""
    if isinstance(data, str):
        text = data
        structured = None
    else:
        text = json.dumps(data, ensure_ascii=False, default=str)
        structured = data if isinstance(data, dict) else {"items": data}
    out = {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}
    if structured is not None and not is_error:
        out["structuredContent"] = json.loads(json.dumps(structured, ensure_ascii=False, default=str))
    return out


class Server:
    """Bộ điều phối JSON-RPC. `registry` là list các dict công cụ (xem tools.TOOLS):
        {"name", "description", "inputSchema", "annotations", "handler"}
    `on_tool_error(exc)` -> chuỗi thông báo cho Claude (endpoint dùng để rollback + làm sạch lỗi frappe).
    """

    def __init__(self, registry, instructions="", version="1", on_tool_error=None):
        self.tools = {t["name"]: t for t in registry}
        self.order = [t["name"] for t in registry]
        self.instructions = instructions
        self.version = version
        self.on_tool_error = on_tool_error or (lambda exc: str(exc) or type(exc).__name__)

    # ------------------------------------------------------------------ public
    def handle(self, payload):
        """dict request -> dict response, hoặc None cho notification (HTTP 202)."""
        method = payload["method"]
        params = payload.get("params") or {}
        if "id" not in payload:
            return None  # notifications/initialized, notifications/cancelled ...
        req_id = payload["id"]
        try:
            return result(req_id, self.dispatch(method, params))
        except ProtocolError as exc:
            return error(req_id, exc.code, exc)

    def dispatch(self, method, params):
        if method == "initialize":
            return {
                "protocolVersion": negotiate(params.get("protocolVersion")),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "title": "eCentric ERP", "version": self.version},
                "instructions": self.instructions,
            }
        if method == "server/discover":
            # Client theo bản 2026-07-28 hỏi trước bản nào được hỗ trợ -> chỉ cho nó lùi về bản cũ.
            return {"supportedVersions": list(SUPPORTED_VERSIONS)}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [self.describe(self.tools[n]) for n in self.order]}
        if method == "tools/call":
            return self.call(params)
        if method in ("resources/list", "resources/templates/list"):
            return {"resources": []} if method == "resources/list" else {"resourceTemplates": []}
        if method == "prompts/list":
            return {"prompts": []}
        raise ProtocolError(METHOD_NOT_FOUND, "Method not found: " + method)

    @staticmethod
    def describe(tool):
        d = {"name": tool["name"], "description": tool["description"],
             "inputSchema": tool.get("inputSchema") or {"type": "object", "properties": {}}}
        if tool.get("title"):
            d["title"] = tool["title"]
        if tool.get("annotations"):
            d["annotations"] = tool["annotations"]
        return d

    def call(self, params):
        name = params.get("name")
        tool = self.tools.get(name)
        if not tool:
            raise ProtocolError(INVALID_PARAMS, "Unknown tool: " + str(name))
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise ProtocolError(INVALID_PARAMS, "arguments must be an object")
        args = clean_args(tool, args)
        try:
            return tool_result(tool["handler"](**args))
        except ToolError as exc:
            return tool_result(self.on_tool_error(exc), is_error=True)
        except Exception as exc:  # lỗi frappe.throw / PermissionError ... -> Claude đọc được, tự sửa
            return tool_result(self.on_tool_error(exc), is_error=True)


def clean_args(tool, args):
    """Chỉ giữ tham số có trong schema (Claude đôi khi gửi thừa), kiểm tham số bắt buộc."""
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    missing = [k for k in schema.get("required") or [] if args.get(k) in (None, "")]
    if missing:
        raise ProtocolError(INVALID_PARAMS, "Missing required argument(s): " + ", ".join(missing))
    return {k: v for k, v in args.items() if k in props}
