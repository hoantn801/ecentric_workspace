# -*- coding: utf-8 -*-
"""Cổng MCP đợt 2 - tệp, lên nháp mọi form, ký số. Chạy KHÔNG cần bench:

    python -m unittest ecentric_workspace.claude_mcp.tests.test_claude_mcp_drafts -v

Kiểm những điều KHÔNG được sai:
  * Ô cam kết / quyết định của người lập (clone_exclude + ai_exclude) không bao giờ đi vào save_draft,
    kể cả khi Claude gửi lên.
  * Select bắt buộc mà máy tự lấp được trả về rỗng (bẫy 23/09 của AI điền hộ).
  * Chỉ gắn được tệp do CHÍNH người dùng tải lên.
  * Không có đường nào gửi phiếu.
  * Toạ độ ô ký từ PDF thật (pypdf) đúng hệ gốc trên-trái theo điểm.
"""
import io
import json
import sys
import types
import unittest

_SAVED, _FAKED = {}, []
CALLS = []
files = approvals = protocol = None
USER = "lan@ecentric.vn"


class _PermErr(Exception):
    pass


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    if name not in _SAVED:
        _SAVED[name] = sys.modules.get(name)
        _FAKED.append(name)
    sys.modules[name] = m
    return m


class _Meta:
    FIELDS = {
        "request_title": ("Data", "Tiêu đề", 0), "payment_amount": ("Currency", "Số tiền", 1),
        "payee_full_name": ("Data", "Người nhận", 1), "is_cost_valid": ("Select", "Chi phí hợp lệ?", 1),
        "details_and_attachments_correct": ("Check", "Tôi xác nhận", 1),
        "request_attachment": ("Attach", "Tệp đính kèm", 1),
    }

    def get_field(self, fn):
        f = self.FIELDS.get(fn)
        return types.SimpleNamespace(fieldtype=f[0], label=f[1], reqd=f[2]) if f else None

    def has_field(self, fn):
        return fn in self.FIELDS


DEF = types.SimpleNamespace(
    code="PAYMENT_REQUEST", business_doctype="EC Payment Request",
    editable_fields=("request_title", "payment_amount", "payee_full_name", "is_cost_valid",
                     "details_and_attachments_correct", "request_attachment"),
    clone_exclude_fields=("details_and_attachments_correct",), ai_exclude_fields=("is_cost_valid",),
    submitter=types.SimpleNamespace(requester_esign=True))

FILES = {
    "F-MINE": {"name": "F-MINE", "file_name": "hop_dong_1.pdf", "file_url": "/private/files/hd1.pdf",
               "owner": USER, "attached_to_doctype": None, "attached_to_name": None},
    "F-OTHER": {"name": "F-OTHER", "file_name": "cua_nguoi_khac.pdf", "file_url": "/private/files/x.pdf",
                "owner": "minh@ecentric.vn", "attached_to_doctype": "EC Payment Request",
                "attached_to_name": "EC-PAYR-1"},
}
DB_SET = []


def setUpModule():
    global files, approvals, protocol
    for k in ("frappe", "frappe.utils", "frappe.sessions"):
        _SAVED[k] = sys.modules.pop(k, None)
        _FAKED.append(k)
    for k in [m for m in list(sys.modules) if m.startswith("ecentric_workspace.claude_mcp") and ".tests" not in m]:
        _SAVED.setdefault(k, sys.modules.pop(k))
        _FAKED.append(k)
    fr = _mod("frappe")
    fr.PermissionError = _PermErr
    fr.ValidationError = type("VE", (Exception,), {})
    fr.session = types.SimpleNamespace(user=USER)
    fr.local = types.SimpleNamespace(message_log=[])
    fr.conf = {}
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.as_json = json.dumps
    fr.parse_json = json.loads
    fr.get_meta = lambda dt: _Meta()

    def get_all(dt, filters=None, fields=None, **k):
        if dt == "File":
            f = filters or {}
            if "name" in f:
                return [FILES[f["name"]]] if f["name"] in FILES else []
            if "attached_to_name" in f:
                return [{"name": "F-MINE", "file_name": "hop_dong_1.pdf"}]
            return [r for r in FILES.values() if all(r.get(a) == b for a, b in f.items() if isinstance(b, str))]
        return []
    fr.get_all = get_all
    fr.db = types.SimpleNamespace(
        exists=lambda dt, n=None: n in FILES if dt == "File" else False,
        get_value=lambda *a, **k: "DNTT - Cty A - 10.000.000",
        set_value=lambda dt, n, fn, v, **k: DB_SET.append((n, fn, v)))
    ut = _mod("frappe.utils", get_url=lambda p="": "https://erp.test" + (p or ""),
              add_to_date=lambda *a, **k: "2026-11-15", now_datetime=lambda: "2026-11-16",
              get_fullname=lambda u: "Lan", nowdate=lambda: "2026-11-16")
    fr.utils = ut

    import ecentric_workspace  # noqa: F401
    pkgs = ("ecentric_workspace.approval_center", "ecentric_workspace.approval_center.api",
            "ecentric_workspace.approval_center.shared", "ecentric_workspace.approval_center.shared.integrations",
            "ecentric_workspace.approval_center.shared.requests", "ecentric_workspace.action_center",
            "ecentric_workspace.platform", "ecentric_workspace.platform.esign")
    for p in pkgs:
        _mod(p).__path__ = []

    schema = ({"fieldname": "request_title", "label": "Tiêu đề", "fieldtype": "Data", "reqd": False},
              {"fieldname": "payment_amount", "label": "Số tiền", "fieldtype": "Currency", "reqd": True},
              {"fieldname": "payee_full_name", "label": "Người nhận", "fieldtype": "Data", "reqd": True})

    def gate(sch, raw):
        names = {s["fieldname"] for s in sch}
        acc = {k: v for k, v in raw.items() if k in names and v not in (None, "")}
        return acc, [{"field": k, "reason": "khong_trong_schema"} for k in raw if k not in names]

    _mod("ecentric_workspace.approval_center.shared.integrations.ai_formfill",
         build_schema=lambda d: schema, gate=gate)
    _mod("ecentric_workspace.approval_center.shared.integrations.ai_attachments",
         may_read=lambda row: row.get("owner") == USER, _content_bytes=lambda n: b"")
    _mod("ecentric_workspace.approval_center.api.ai_formfill",
         _require_form_open=lambda code: CALLS.append(("form_open", code)),
         _o_bat_buoc_may_tu_dien=lambda d: ["is_cost_valid"],
         _con_thieu=lambda d, n: [{"fieldname": "payee_full_name", "label": "Người nhận"},
                                  {"fieldname": "is_cost_valid", "label": "Chi phí hợp lệ?"}])

    def get_definition(code):
        if code != "PAYMENT_REQUEST":
            raise KeyError(code)
        return DEF
    _mod("ecentric_workspace.approval_center.shared.registry", get_definition=get_definition,
         get_definition_for_doctype=lambda dt: DEF if dt == DEF.business_doctype else (_ for _ in ()).throw(KeyError(dt)))

    def save_draft(definition, name=None, payload=None):
        CALLS.append(("save_draft", name, payload))
        return {"name": name or "EC-PAYR-0099"}
    _mod("ecentric_workspace.approval_center.shared.requests.command_service", save_draft=save_draft)
    _mod("ecentric_workspace.action_center.resolvers",
         build_approval_url=lambda dt, n: "/approvals/payment-request?id=" + n)

    from ecentric_workspace.claude_mcp import approvals as a, files as f, protocol as p
    approvals, files, protocol = a, f, p


def tearDownModule():
    for k in _FAKED:
        sys.modules.pop(k, None)
        if _SAVED.get(k) is not None:
            sys.modules[k] = _SAVED[k]


class TestDrafts(unittest.TestCase):
    def setUp(self):
        CALLS.clear()
        DB_SET.clear()

    def test_commitment_fields_never_reach_save_draft(self):
        res = approvals.create_draft_request(
            "PAYMENT_REQUEST",
            fields={"payment_amount": 10000000, "request_title": "HĐ 01",
                    "is_cost_valid": "Yes", "details_and_attachments_correct": 1},
            files=["F-MINE"])
        payload = [c for c in CALLS if c[0] == "save_draft"][0][2]
        self.assertNotIn("is_cost_valid", payload)
        self.assertNotIn("details_and_attachments_correct", payload)
        self.assertEqual(payload["payment_amount"], 10000000)
        # tệp: vào _attachments + ô Attach đầu tiên
        self.assertEqual(payload["_attachments"], [{"url": "/private/files/hd1.pdf", "name": "hop_dong_1.pdf"}])
        self.assertEqual(payload["request_attachment"], "/private/files/hd1.pdf")
        # Select bắt buộc máy tự lấp -> rỗng
        self.assertIn(("EC-PAYR-0099", "is_cost_valid", ""), DB_SET)
        # ô thiếu tách đúng hai nhóm
        self.assertEqual([m["field"] for m in res["missing_ask_user"]], ["payee_full_name"])
        self.assertEqual([m["field"] for m in res["missing_user_fills_on_web"]], ["is_cost_valid"])
        self.assertEqual(res["reference"], "EC Payment Request/EC-PAYR-0099")
        self.assertIn(("form_open", "PAYMENT_REQUEST"), CALLS)
        self.assertTrue(res["link"].startswith("https://erp.test/"))

    def test_cannot_attach_someone_elses_file(self):
        with self.assertRaises(protocol.ToolError):
            approvals.create_draft_request("PAYMENT_REQUEST", fields={"payment_amount": 1}, files=["F-OTHER"])
        self.assertFalse([c for c in CALLS if c[0] == "save_draft"])

    def test_unknown_form(self):
        with self.assertRaises(protocol.ToolError):
            approvals.get_form("KHONG_CO")

    def test_update_requires_something(self):
        with self.assertRaises(protocol.ToolError):
            approvals.update_draft_request("EC Payment Request/EC-PAYR-0099", fields={"is_cost_valid": "Yes"})
        approvals.update_draft_request("EC Payment Request/EC-PAYR-0099", fields={"payee_full_name": "Cty A"})
        self.assertEqual(CALLS[-1][1:], ("EC-PAYR-0099", {"payee_full_name": "Cty A"}))

    def test_get_form_lists_user_only_fields_and_esign(self):
        out = approvals.get_form("PAYMENT_REQUEST")
        self.assertEqual({u["field"] for u in out["user_must_fill_on_web"]},
                         {"is_cost_valid", "details_and_attachments_correct"})
        self.assertTrue(out["digital_signature"])
        self.assertEqual(out["attachment_fields"][0]["field"], "request_attachment")

    def test_no_submit_tool_anywhere(self):
        import re
        from ecentric_workspace.claude_mcp import tools
        names = [t["name"] for t in tools.TOOLS]
        self.assertFalse([n for n in names if re.search(r"submit|approve|reject|send_request|delete", n)])
        self.assertIn("create_draft_request", names)


class TestPdfAnchors(unittest.TestCase):
    def setUp(self):
        try:
            from reportlab.pdfgen import canvas  # noqa: F401
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("cần reportlab + pypdf")

    def pdf(self):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.drawString(72, 800, "HOP DONG DICH VU")
        c.showPage()
        c.drawString(80, 300, "DAI DIEN BEN A")
        c.drawString(350, 300, "DAI DIEN BEN B")
        c.save()
        return buf.getvalue()

    def test_positions_top_left_points(self):
        pos = files.text_positions(self.pdf())
        b = [p for p in pos if p["text"] == "DAI DIEN BEN B"][0]
        self.assertEqual((b["page"], b["x"]), (2, 350.0))
        self.assertAlmostEqual(b["top"], 841.9 - 300, delta=1)

    def test_anchors_and_box(self):
        anchors = files.signature_anchors(self.pdf())
        self.assertEqual([a["text"] for a in anchors], ["DAI DIEN BEN A", "DAI DIEN BEN B"])
        box = files.box_under(anchors[1])
        self.assertEqual(box["page_index"], 2)
        self.assertGreater(box["y"], anchors[1]["top"])          # nằm DƯỚI dòng chữ
        self.assertLessEqual(box["x"] + box["width"], anchors[1]["page_w"])

    def test_docx_and_xlsx_text(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Bên A: Cty X</w:t></w:r></w:p>"
                                            "<w:p><w:r><w:t>Giá trị: 10.000.000</w:t></w:r></w:p></w:document>")
        self.assertEqual(files.docx_text(buf.getvalue()), "Bên A: Cty X\nGiá trị: 10.000.000")
        try:
            from openpyxl import Workbook
        except ImportError:
            return
        wb = Workbook()
        wb.active.append(["Mã", "Số tiền"])
        wb.active.append(["HD01", 5000])
        out = io.BytesIO()
        wb.save(out)
        self.assertIn("HD01\t5000", files.xlsx_text(out.getvalue()))


if __name__ == "__main__":
    unittest.main()
