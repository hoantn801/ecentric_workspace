# Copyright (c) 2026, eCentric and contributors
"""Chan ky hong VINH VIEN luc tao chung tu (413, 00044 07/09) phai co duong ra.

  1. state: Permanent Failure -> Queued (chi qua retry).
  2. service.retry_signature_request: cho Permanent Failure CHI khi may_have_sent False;
     Manual Review / Retryable Failure nhu cu; trang thai khac tu choi (code THAT, frappe gia).
  3. tasks: Permanent Failure cua chan NGUOI DE NGHI -> _complete_dsr (reconcile -> AR
     "Failed" + thong bao), khong con ket "Processing" im lang (AST).
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


class TestState(unittest.TestCase):
    def test_permanent_failure_co_canh_queued(self):
        m = types.ModuleType("st")
        src = _read("platform", "esign", "state.py")
        fk = types.ModuleType("frappe"); fk._ = lambda s: s
        saved = sys.modules.get("frappe"); sys.modules["frappe"] = fk
        try:
            exec(compile(src, "state.py", "exec"), m.__dict__)
        finally:
            if saved is None: sys.modules.pop("frappe", None)
            else: sys.modules["frappe"] = saved
        self.assertEqual(m.DSR_TRANSITIONS["Permanent Failure"], ("Queued",))


def _retry(status, accepted_at=None, txn=None):
    src = _read("platform", "esign", "service.py")
    tree = ast.parse(src)
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "retry_signature_request"][0]
    calls = []
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.throw = lambda msg, *a, **k: (_ for _ in ()).throw(Exception(msg))
    fk.db = types.SimpleNamespace(get_value=lambda dt, n, f=None, as_dict=False, **k:
                                  {"status": status, "accepted_at": accepted_at, "bulk_job_transaction_id": txn} if as_dict else 1,
                                  set_value=lambda *a, **k: calls.append(("set", a)))
    fk.enqueue = lambda *a, **k: calls.append(("enqueue", k.get("dsr_name")))
    ns = {"frappe": fk, "_": lambda s: s, "DSR": "DSR",
          "perms": types.SimpleNamespace(assert_system_manager=lambda: None),
          "sm": types.SimpleNamespace(may_have_sent=lambda r: bool(r.get("accepted_at") or r.get("bulk_job_transaction_id")),
                                      SIGNING_QUEUE="q", SIGNING_JOB_TIMEOUT=1),
          "events": types.SimpleNamespace(set_dsr_status=lambda *a, **k: calls.append(("status", a[1]))),
          "now_datetime": lambda: "now"}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "svc.py", "exec"), ns)
    return ns["retry_signature_request"], calls


class TestRetry(unittest.TestCase):
    def test_permanent_failure_chua_gui_thi_retry_duoc(self):
        f, calls = _retry("Permanent Failure")
        self.assertEqual(f("DSR-33"), {"queued": True})
        self.assertIn(("status", "Queued"), calls); self.assertIn(("enqueue", "DSR-33"), calls)

    def test_permanent_failure_da_gui_thi_tu_choi(self):
        f, calls = _retry("Permanent Failure", accepted_at="2026-09-07 11:57")
        with self.assertRaises(Exception) as cm:
            f("DSR-33")
        self.assertIn("Đối soát", str(cm.exception)); self.assertEqual(calls, [])

    def test_manual_review_va_retryable_nhu_cu(self):
        for st in ("Manual Review", "Retryable Failure"):
            f, calls = _retry(st)
            self.assertEqual(f("DSR-1"), {"queued": True})

    def test_trang_thai_khac_tu_choi(self):
        for st in ("Approval Completed", "Verifying", "Cancelled"):
            f, calls = _retry(st)
            with self.assertRaises(Exception):
                f("DSR-1")
            self.assertEqual(calls, [])


class TestRequesterNotified(unittest.TestCase):
    def test_permanent_failure_requester_goi_complete_dsr(self):
        src = _read("platform", "esign", "tasks.py")
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "process_signing_request"][0]
        body = ast.unparse(fn)
        i = body.index("target = 'Retryable Failure' if e.retryable else 'Permanent Failure'")
        tail = body[i:i + 1400]
        self.assertIn("if not e.retryable and (dsr or {}).get('actor_type') == 'Requester':", tail)
        self.assertIn("_complete_dsr(dsr_name, dsr)", tail)


if __name__ == "__main__":
    unittest.main()
