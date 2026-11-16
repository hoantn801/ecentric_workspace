# -*- coding: utf-8 -*-
"""Cổng MCP cho Claude - test chạy KHÔNG cần bench:

    python -m unittest ecentric_workspace.claude_mcp.tests.test_claude_mcp -v

Dùng một `frappe` giả tối thiểu (chỉ những gì tools.py chạm tới) + các module PM giả,
để kiểm: giao thức JSON-RPC, tham số đi ĐÚNG vào hàm mà màn hình web gọi, lỗi trả về
cho Claude đọc (isError) thay vì vỡ request, và danh sách công cụ không lọt công cụ duyệt phiếu."""
import json
import sys
import types
import unittest


# ------------------------------------------------------------------ frappe giả
class _PermErr(Exception):
    pass


class _ValErr(Exception):
    pass


def _install_fake_frappe():
    fr = types.ModuleType("frappe")
    fr.PermissionError = _PermErr
    fr.ValidationError = _ValErr
    fr.DoesNotExistError = type("DoesNotExistError", (_ValErr,), {})
    fr.session = types.SimpleNamespace(user="lan@ecentric.vn")
    fr.local = types.SimpleNamespace(message_log=[])
    fr.conf = {}
    fr.as_json = lambda v: json.dumps(v)
    fr.parse_json = lambda v: json.loads(v)
    fr.whitelist = lambda *a, **k: (lambda f: f)
    utils = types.ModuleType("frappe.utils")
    utils.get_url = lambda p="": "https://erp.test" + (p or "")
    utils.get_fullname = lambda u: "Lan"
    utils.nowdate = lambda: "2026-11-16"
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    return fr


CALLS = []
_SAVED = {}
_FAKED = ("frappe", "frappe.utils", "ecentric_workspace.pm", "ecentric_workspace.pm.api",
          "ecentric_workspace.pm.api.queue", "ecentric_workspace.pm.api.tasks",
          "ecentric_workspace.pm.api.assignment", "ecentric_workspace.pm.api.pm_inbox",
          "ecentric_workspace.pm.api.comments", "ecentric_workspace.claude_mcp.tools",
          "ecentric_workspace.claude_mcp.protocol", "ecentric_workspace.claude_mcp.endpoint")


def _mod(name, **fns):
    m = types.ModuleType(name)
    for k, v in fns.items():
        setattr(m, k, v)
    sys.modules[name] = m
    parent, _, child = name.rpartition(".")
    if parent in sys.modules:
        setattr(sys.modules[parent], child, m)
    return m


def _rec(label, ret):
    def f(*a, **k):
        CALLS.append((label, a, k))
        if isinstance(ret, Exception):
            raise ret
        return ret(*a, **k) if callable(ret) else ret
    return f


protocol = tools = None


def setUpModule():
    """Cài frappe + module PM giả CHỈ trong lúc chạy file này, rồi trả lại sys.modules như cũ
    (để `bench run-tests` hay bộ chạy khác trong cùng tiến trình không dính frappe giả)."""
    global protocol, tools
    for k in _FAKED:
        _SAVED[k] = sys.modules.pop(k, None)
    _install_fake_frappe()
    import ecentric_workspace  # noqa: F401  gói thật
    for pkg in ("ecentric_workspace.pm", "ecentric_workspace.pm.api"):
        _mod(pkg)
        sys.modules[pkg].__path__ = []

    QUEUE_ROWS = [
        {"rank": 1, "name": "TASK-1", "subject": "Gửi báo cáo GMV", "bucket": "late", "due": "2026-11-14",
         "due_time": "", "priority": "High", "workflow_state": "To Do", "project_name": "",
         "giver_name": "Hoàn", "self": False, "assignees": [{"name": "Lan"}], "awaiting": 0},
        {"rank": 2, "name": "TASK-2", "subject": "Họp brand", "bucket": "today", "due": "2026-11-16",
         "due_time": "15:00", "priority": "Medium", "workflow_state": "In Progress", "self": True,
         "assignees": [{"name": "Lan"}]},
    ]

    _mod("ecentric_workspace.pm.api.queue", list=_rec("queue.list", {
        "today": "2026-11-16", "rows": QUEUE_ROWS, "counts": {"late": 1, "today": 1, "none": 0},
        "buckets": [{"key": "late", "label": "Quá hạn"}, {"key": "today", "label": "Hôm nay"}],
        "asks": [{"request": "PAR-1", "task": "TASK-9", "subject": "Làm slide", "from_name": "Minh",
                  "proposed_end": "2026-11-20"}], "waiting": []}))
    _mod("ecentric_workspace.pm.api.tasks",
         create=_rec("tasks.create", {"name": "TASK-NEW", "subject": "x"}),
         mark_done=_rec("tasks.mark_done", {"state": "Done"}),
         set_status=_rec("tasks.set_status", None),
         get=_rec("tasks.get", {"task": {"name": "TASK-1", "subject": "Gửi báo cáo GMV",
                                         "workflow_state": "To Do", "_assign": '["lan@ecentric.vn"]',
                                         "description": "<p>Chi tiết <b>A</b></p>",
                                         "giver": {"user": "hoan@ecentric.vn", "full_name": "Hoàn"}},
                                "subtasks": [], "user_names": {"lan@ecentric.vn": "Lan"}}))
    _mod("ecentric_workspace.pm.api.assignment",
         create_with_task=_rec("assignment.create_with_task", {"task": "TASK-REQ", "request": {}}),
         list_assignable=_rec("assignment.list_assignable", {"rows": [
             {"email": "lan.nguyen@ecentric.vn", "full_name": "Nguyễn Thị Lan"},
             {"email": "lan.tran@ecentric.vn", "full_name": "Trần Ngọc Lan"},
             {"email": "minh@ecentric.vn", "full_name": "Lê Văn Minh"}]}))
    _mod("ecentric_workspace.pm.api.pm_inbox",
         request_deadline=_rec("pm_inbox.request_deadline", {}),
         nudge=_rec("pm_inbox.nudge", {"task": "TASK-1", "sent": ["lan@ecentric.vn"], "skipped": []}))
    _mod("ecentric_workspace.pm.api.comments",
         add=_rec("comments.add", {"name": "CMT-1"}),
         list=_rec("comments.list", {"rows": []}))
    from ecentric_workspace.claude_mcp import protocol as _p, tools as _t
    protocol, tools = _p, _t


def tearDownModule():
    import ecentric_workspace
    for k in _FAKED:
        sys.modules.pop(k, None)
        if _SAVED.get(k) is not None:
            sys.modules[k] = _SAVED[k]
    if _SAVED.get("ecentric_workspace.pm") is not None:
        ecentric_workspace.pm = _SAVED["ecentric_workspace.pm"]
    elif hasattr(ecentric_workspace, "pm"):
        del ecentric_workspace.pm




def server():
    return protocol.Server(tools.TOOLS, instructions="hi", version="t")


def call(name, **args):
    return server().handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                            "params": {"name": name, "arguments": args}})["result"]


def payload(res):
    return json.loads(res["content"][0]["text"])


class TestProtocol(unittest.TestCase):
    def test_initialize_negotiates_version(self):
        s = server()
        r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18"}})["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["capabilities"])
        r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2099-01-01"}})["result"]
        self.assertEqual(r["protocolVersion"], protocol.DEFAULT_VERSION)

    def test_notification_has_no_response(self):
        self.assertIsNone(server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method(self):
        r = server().handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
        self.assertEqual(r["error"]["code"], protocol.METHOD_NOT_FOUND)

    def test_parse_rejects_garbage_and_batch(self):
        for body in (b"{", b"[]", b'{"jsonrpc":"1.0","method":"x"}', b'{"jsonrpc":"2.0","id":true,"method":"x"}'):
            with self.assertRaises(protocol.ProtocolError):
                protocol.parse(body)
        self.assertEqual(protocol.parse(b'{"jsonrpc":"2.0","id":1,"method":"ping"}')["id"], 1)

    def test_tools_list_names_valid_and_no_approve_tool(self):
        r = server().handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]
        names = [t["name"] for t in r["tools"]]
        self.assertEqual(len(names), len(set(names)))
        import re
        for t in r["tools"]:
            self.assertRegex(t["name"], r"^[a-zA-Z0-9_-]{1,64}$")
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertIn("readOnlyHint", t["annotations"])
        # Hoàn chốt 16/11: đợt 1 không duyệt/từ chối phiếu, không xoá
        self.assertFalse([n for n in names if re.search(r"approve|reject|delete|cancel", n)])
        reads = {t["name"] for t in r["tools"] if t["annotations"]["readOnlyHint"]}
        self.assertTrue({"my_action_items", "my_requests", "get_request",
                         "list_weekly_reports", "get_weekly_report"} <= reads)

    def test_missing_required_arg_is_protocol_error(self):
        r = server().handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                             "params": {"name": "get_task", "arguments": {}}})
        self.assertEqual(r["error"]["code"], protocol.INVALID_PARAMS)

    def test_extra_args_dropped(self):
        CALLS.clear()
        call("complete_task", task="TASK-1", user="sep@ecentric.vn")  # không ai đổi được người dùng
        self.assertEqual(CALLS[-1], ("tasks.mark_done", ("TASK-1",), {}))

    def test_tool_exception_becomes_is_error(self):
        sys.modules["ecentric_workspace.pm.api.tasks"].mark_done = _rec("x", _PermErr("Không phải việc của bạn"))
        try:
            r = call("complete_task", task="TASK-1")
        finally:
            sys.modules["ecentric_workspace.pm.api.tasks"].mark_done = _rec("tasks.mark_done", {"state": "Done"})
        self.assertTrue(r["isError"])
        self.assertIn("Không phải việc của bạn", r["content"][0]["text"])


class TestPmTools(unittest.TestCase):
    def setUp(self):
        CALLS.clear()

    def test_my_tasks_keeps_server_order_and_links(self):
        out = payload(call("my_tasks"))
        self.assertEqual([t["task"] for t in out["tasks"]], ["TASK-1", "TASK-2"])
        self.assertEqual(out["tasks"][0]["link"], "https://erp.test/pm#task/TASK-1")
        self.assertEqual(out["counts"], {"Quá hạn": 1, "Hôm nay": 1})
        self.assertEqual(out["tasks"][1]["giver"], "(tự giao)")
        self.assertEqual(out["needs_my_acceptance"][0]["from"], "Minh")
        self.assertEqual(CALLS[0], ("queue.list", (), {"tab": "me", "include_personal": 0}))

    def test_my_tasks_give_tab(self):
        call("my_tasks", view="give", limit=1)
        self.assertEqual(CALLS[0][2]["tab"], "give")

    def test_get_task_reads_nested_shape(self):
        out = payload(call("get_task", task="TASK-1"))
        self.assertEqual(out["giver"], "Hoàn")
        self.assertEqual(out["assignees"], ["Lan"])
        self.assertEqual(out["description"], "Chi tiết A")

    def test_find_people_accent_insensitive(self):
        out = payload(call("find_people", query="lan"))
        self.assertEqual({m["email"] for m in out["matches"]}, {"lan.nguyen@ecentric.vn", "lan.tran@ecentric.vn"})
        out = payload(call("find_people", query="@Minh"))
        self.assertEqual(out["matches"][0]["email"], "minh@ecentric.vn")

    def test_create_task_direct_mirrors_quick_assign(self):
        out = payload(call("create_task", subject="Gửi báo cáo", assignees=["minh@ecentric.vn"],
                           due_date="2026-11-20", due_time="9:30", priority="cao"))
        label, _a, k = CALLS[-1]
        self.assertEqual(label, "tasks.create")
        self.assertEqual(k["project"], "")
        self.assertEqual(json.loads(k["assignees"]), ["minh@ecentric.vn"])
        self.assertEqual((k["exp_end_date"], k["pm_end_time"], k["priority"]), ("2026-11-20", "09:30:00", "High"))
        self.assertIsNone(k["split_per_assignee"])
        self.assertEqual(out["task"], "TASK-NEW")

    def test_create_task_defaults_to_self(self):
        call("create_task", subject="Tự nhắc")
        self.assertEqual(json.loads(CALLS[-1][2]["assignees"]), ["lan@ecentric.vn"])
        self.assertEqual(CALLS[-1][2]["priority"], "Medium")

    def test_create_task_need_acceptance(self):
        call("create_task", subject="Làm slide", assignees=["minh@ecentric.vn"], due_date="2026-11-20",
             need_acceptance=True)
        label, _a, k = CALLS[-1]
        self.assertEqual(label, "assignment.create_with_task")
        self.assertEqual((k["recipient"], k["proposed_end"]), ("minh@ecentric.vn", "2026-11-20 18:00:00"))
        call("create_task", subject="Làm slide", assignees=["minh@ecentric.vn", "lan.tran@ecentric.vn"],
             need_acceptance=True)
        self.assertEqual(CALLS[-1][2]["split_per_assignee"], 1)

    def test_create_task_validation_is_error_not_crash(self):
        r = call("create_task", subject="X", assignees=["Minh"])
        self.assertTrue(r["isError"])
        self.assertIn("find_people", r["content"][0]["text"])
        r = call("create_task", subject="X", due_date="20/11/2026")
        self.assertTrue(r["isError"])
        self.assertFalse([c for c in CALLS if c[0] == "tasks.create"])

    def test_complete_task_blocked_reason(self):
        sys.modules["ecentric_workspace.pm.api.tasks"].mark_done = _rec(
            "tasks.mark_done", {"state": "To Do", "blocked_reason": "open_children", "missing": 2})
        try:
            r = call("complete_task", task="TASK-1")
        finally:
            sys.modules["ecentric_workspace.pm.api.tasks"].mark_done = _rec("tasks.mark_done", {"state": "Done"})
        self.assertTrue(r["isError"])
        self.assertIn("2 việc con", r["content"][0]["text"])

    def test_start_request_deadline_nudge_comment(self):
        call("start_task", task="TASK-1")
        self.assertEqual(CALLS[-1], ("tasks.set_status", ("TASK-1", "In Progress"), {}))
        call("request_deadline_change", task="TASK-1", new_due="2026-11-25", reason="Chờ số liệu")
        self.assertEqual(CALLS[-1], ("pm_inbox.request_deadline", ("TASK-1", "2026-11-25", "Chờ số liệu"), {}))
        out = payload(call("remind_assignees", task="TASK-1"))
        self.assertEqual(out["reminded"], ["lan@ecentric.vn"])
        call("comment_on_task", task="TASK-1", text="<script>x</script>\nOK")
        self.assertEqual(CALLS[-1][1][2], "&lt;script&gt;x&lt;/script&gt;<br>OK")


class TestEndpoint(unittest.TestCase):
    """endpoint.handle: bật/tắt, 401 kèm WWW-Authenticate, danh sách thử nghiệm, 202 cho notification."""

    def setUp(self):
        try:
            import werkzeug.wrappers  # noqa: F401
        except ImportError:
            self.skipTest("werkzeug không có (bench luôn có)")
        FR = sys.modules["frappe"]
        FR.conf = {"ec_claude_mcp": 1}
        FR.session.user = "lan@ecentric.vn"
        FR.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
        FR.db = types.SimpleNamespace(rollback=lambda: None)
        FR.log_error = lambda *a, **k: None
        FR.get_traceback = lambda: ""
        from ecentric_workspace.claude_mcp import endpoint
        self.ep = endpoint
        self.FR = FR

    def req(self, body, method="POST"):
        data = json.dumps(body).encode() if not isinstance(body, bytes) else body
        self.FR.request = types.SimpleNamespace(method=method, url="https://team.test/api/method/x",
                                                get_data=lambda: data)
        return self.ep.handle(cmd="x", method="ignored")

    def test_disabled_is_404(self):
        self.FR.conf = {}
        self.assertEqual(self.req({"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 404)

    def test_guest_gets_401_with_resource_metadata(self):
        self.FR.session.user = "Guest"
        r = self.req({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(r.status_code, 401)
        self.assertIn('resource_metadata="https://team.test/.well-known/oauth-protected-resource"',
                      r.headers["WWW-Authenticate"])

    def test_pilot_allowlist(self):
        self.FR.conf = {"ec_claude_mcp": 1, "ec_claude_mcp_users": ["hoan@ecentric.vn"]}
        self.assertEqual(self.req({"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 403)
        self.FR.conf["ec_claude_mcp_users"] = "hoan@ecentric.vn, lan@ecentric.vn"
        self.assertEqual(self.req({"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 200)

    def test_get_is_405_and_notification_202_and_bad_json_400(self):
        self.assertEqual(self.req(b"", method="GET").status_code, 405)
        self.assertEqual(self.req({"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code, 202)
        self.assertEqual(self.req(b"{oops").status_code, 400)

    def test_initialize_returns_raw_jsonrpc(self):
        r = self.req({"jsonrpc": "2.0", "id": "a", "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18"}})
        body = json.loads(r.get_data())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(body["id"], "a")
        self.assertIn("eCentric", body["result"]["instructions"])


class TestHelpers(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(tools.fold("Đặng Thị Ánh"), "dang thi anh")

    def test_priority(self):
        self.assertEqual(tools.norm_priority("gấp"), "Urgent")
        self.assertEqual(tools.norm_priority("high"), "High")
        with self.assertRaises(protocol.ToolError):
            tools.norm_priority("siêu cao")

    def test_tool_result_shape(self):
        r = protocol.tool_result({"a": "ư"})
        self.assertEqual(r["structuredContent"], {"a": "ư"})
        self.assertIn("ư", r["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
