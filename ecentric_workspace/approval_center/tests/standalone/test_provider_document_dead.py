# Copyright (c) 2026, eCentric and contributors
"""Chung tu ben SCTS bi HUY / XOA giua chung (06/09).

Hoan: nguoi tao (Hien) van thay nut "Xoa" va "Huy chung tu" tren cong eContract o moi buoc.
ERP khong dieu khien duoc nut do; ERP phai NHAN RA va dung ro rang:

  1. tasks._poll_or_stop (code THAT, adapter gia): status cancelled/rejected hoac 404 ->
     Permanent Failure, error_code provider_document_*, ghi len GOI, tao ToDo; con song ->
     tra doc_state (khong poll lan hai).
  2. service.approve_and_sign tu choi khi goi mang provider_document_*; signing_readiness
     co check provider_document_alive trong required (AST).
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_PKG = os.path.join(_APP, "ecentric_workspace")


def _read(*parts):
    with io.open(os.path.join(_PKG, *parts), encoding="utf-8") as fh:
        return fh.read()


class _PErr(Exception):
    def __init__(self, code, msg="", retryable=False, ambiguous=False):
        super().__init__(msg); self.code = code; self.retryable = retryable; self.ambiguous = ambiguous


def _tasks():
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.set_values = []; fk.todos = []
    fk.conf = {}
    fk.db = types.SimpleNamespace(set_value=lambda dt, n, v=None, *a, **k: fk.set_values.append((dt, n, v)),
                                  get_value=lambda *a, **k: None, exists=lambda *a, **k: True,
                                  count=lambda *a, **k: 0)
    fk.get_all = lambda *a, **k: []
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk.session = types.SimpleNamespace(user="Administrator")
    utils = types.ModuleType("frappe.utils"); utils.add_to_date = lambda *a, **k: None; utils.now_datetime = lambda: "now"
    ev = types.ModuleType("events"); ev.calls = []
    ev.set_dsr_status = lambda name, status, **k: ev.calls.append(("set", name, status, k))
    ev.emit = lambda *a, **k: ev.calls.append(("emit", a, k))
    base = types.ModuleType("base"); base.ProviderError = _PErr
    base.SignatureProviderAdapter = type("A", (), {}); base.VerificationResult = type("V", (), {})
    prov = types.ModuleType("providers"); prov.get_adapter = lambda s: None
    san = types.ModuleType("sanitize"); san.safe_error = lambda e: "safe:" + str(e)
    mods = {"frappe": fk, "frappe.utils": utils,
            "ecentric_workspace.platform.esign.binding": types.ModuleType("b"),
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.package": types.ModuleType("p"),
            "ecentric_workspace.platform.esign.service": types.ModuleType("s"),
            "ecentric_workspace.platform.esign.state": types.ModuleType("st"),
            "ecentric_workspace.platform.esign.providers": prov,
            "ecentric_workspace.platform.esign.providers.base": base,
            "ecentric_workspace.platform.esign.sanitize": san}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_tasks_under_test")
        exec(compile(_read("platform", "esign", "tasks.py"), "tasks.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._dead_letter_todo = lambda name: fk.todos.append(name)
    m._fk = fk; m._ev = ev
    return m


def _adapter(status=None, raise_code=None):
    class A(object):
        def poll_status(self, doc_id):
            if raise_code:
                raise _PErr(raise_code, "x", retryable=False)
            return types.SimpleNamespace(status=status, document_id=doc_id, signers=[], files=[])
    return A()


DSR = types.SimpleNamespace(package="PKG-1")


class TestPollOrStop(unittest.TestCase):
    def test_con_song_thi_tra_doc_state_khong_ghi_gi(self):
        m = _tasks()
        ds = m._poll_or_stop("DSR-1", DSR, _adapter("processing"), "doc-1")
        self.assertEqual(ds.status, "processing")
        self.assertEqual(m._fk.set_values, []); self.assertEqual(m._ev.calls, []); self.assertEqual(m._fk.todos, [])

    def test_bi_huy_thi_permanent_failure_ghi_goi_va_todo(self):
        m = _tasks()
        self.assertIsNone(m._poll_or_stop("DSR-1", DSR, _adapter("cancelled"), "doc-1"))
        self.assertEqual(m._fk.set_values[0][:2], ("EC Digital Signature Package", "PKG-1"))
        self.assertEqual(m._fk.set_values[0][2]["error_code"], "provider_document_cancelled")
        self.assertIn("huỷ", m._fk.set_values[0][2]["error_message"])
        st = [c for c in m._ev.calls if c[0] == "set"][0]
        self.assertEqual(st[2], "Permanent Failure")
        self.assertEqual(st[3]["extra_fields"]["error_code"], "provider_document_cancelled")
        self.assertEqual(st[3]["extra_fields"]["retryable"], 0)
        self.assertEqual(m._fk.todos, ["DSR-1"])

    def test_bi_tu_choi_tren_cong_cung_dung(self):
        m = _tasks()
        self.assertIsNone(m._poll_or_stop("DSR-1", DSR, _adapter("REJECTED"), "doc-1"))
        self.assertEqual(m._fk.set_values[0][2]["error_code"], "provider_document_rejected")

    def test_404_thi_la_xoa(self):
        m = _tasks()
        self.assertIsNone(m._poll_or_stop("DSR-1", DSR, _adapter(raise_code="scts_document_not_found"), "doc-1"))
        self.assertEqual(m._fk.set_values[0][2]["error_code"], "provider_document_deleted")
        self.assertIn("xoá", m._fk.set_values[0][2]["error_message"])

    def test_loi_khac_thi_nem_len_nhu_cu(self):
        m = _tasks()
        with self.assertRaises(_PErr):
            m._poll_or_stop("DSR-1", DSR, _adapter(raise_code="scts_auth_error_401"), "doc-1")
        self.assertEqual(m._fk.set_values, [])


class TestWiring(unittest.TestCase):
    def test_process_dung_ket_qua_poll_mot_lan(self):
        src = _read("platform", "esign", "tasks.py")
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)
              and n.name == "process_signing_request"][0]
        body = ast.unparse(fn)
        i = body.index("doc_state = _poll_or_stop(dsr_name, dsr, adapter, doc_id)")
        j = body.index("may_have_sent = sm.may_have_sent(dsr)")
        self.assertLess(i, j)
        self.assertIn("if doc_state is None:\n            return", body)
        self.assertEqual(body.count("adapter.poll_status(doc_id)"), 1, "chi poll lai MOT lan sau khi gui")

    def test_service_tu_choi_va_readiness_co_check(self):
        src = _read("platform", "esign", "service.py")
        tree = ast.parse(src)
        a = ast.unparse([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "approve_and_sign"][0])
        self.assertIn("startswith('provider_document_')", a)
        i = a.index("startswith('provider_document_')"); j = a.index("recomputed = pkgsvc.compute_hash(pkg_name)")
        self.assertLess(i, j, "tu choi TRUOC khi lam gi khac")
        r = ast.unparse([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "signing_readiness"][0])
        self.assertIn("checks['provider_document_alive'] = bool(pkg) and (not dead)", r)
        self.assertIn("'provider_document_alive'", r.split("required = ")[1][:300])


if __name__ == "__main__":
    unittest.main()
