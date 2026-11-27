# Copyright (c) 2026, eCentric and contributors
"""QC 27/11/2026 (EC-CTR-2026-00150): lich su phieu ghi dong "Bo qua cap nay - Cap Nhan su chi danh cho hop dong
lao dong" voi TEN NGUOI GUI va dung TRUOC "Da duyet - Cap 1" -> nguoi duyet tuong nguoi gui tu bo cap.

  * engine.submit (skip_level_nos): dong Skipped ghi actor "Administrator" (giao dien: "He thong"), gan level_no /
    level_name cua cap bi bo; comment chi con ly do. Ap dung moi form dung skip_level_nos (hop dong, brand weight,
    offer, promotion) - deu la bo cap theo dieu kien nghiep vu, khong ai bam.
  * get_detail tra level_name cua dong lich su (cap bi bo khong co request_level).
  * EcApprovalUI: dong cu (actor = nguoi gui, "(level 4 - ...)" o cuoi comment) va dong moi deu hien "Tu dong bo
    qua cap nay · Cap 4 · ... · He thong", va xep vao cho cua cap 4 (jsdom: test_lich_su_bo_cap.js).
Chay: python -m pytest ecentric_workspace/approval_center/tests/standalone/test_lich_su_bo_cap_27_11.py
"""
import ast
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def _read(*parts):
    with open(os.path.join(APP, *parts), encoding="utf-8") as f:
        return f.read()


def _load_submit(log):
    """Chay `submit` THAT cua transitions.py tren frappe gia - chi ghi lai log_action."""
    src = _read("approval_center", "shared", "workflow", "transitions.py")
    tree = ast.parse(src)
    seg = [ast.get_source_segment(src, n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "submit"]
    assert len(seg) == 1

    class _Req(dict):
        __getattr__ = dict.get

        def insert(self, **kw):
            self["name"] = "AR-1"
            return self

    levels = [types.SimpleNamespace(level_no=n, level_name=nm, mandatory=0) for n, nm in
              ((1, "Department Manager Review"), (2, "Finance Team Review"), (3, "Head of Finance Review"),
               (4, "HR & C&B Review"), (5, "CEO Review"))]
    fk = types.SimpleNamespace(get_doc=lambda d: _Req(d), throw=lambda m: (_ for _ in ()).throw(Exception(m)))
    ns = {"frappe": fk, "_": lambda s: s, "now_datetime": lambda: "2026-11-27 10:00:00",
          "resolve_process": lambda t, c: types.SimpleNamespace(name="CONTRACT_REVIEW-V2", version_no=2),
          "resolve_levels": lambda p: list(levels),
          "resolve_requester_department": lambda *a: "Sales - EC",
          "build_snapshot": lambda req, p, lv, r: None, "add_watchers": lambda *a, **k: None,
          "_apply_sla_overrides": lambda *a: None, "_activate_level": lambda *a: None,
          "_request_levels": lambda n: [types.SimpleNamespace(level_no=1)],
          "_notify_watchers": lambda *a: None, "_watch_label": lambda r: "",
          "log_action": lambda *a, **k: log.append((a, k))}
    exec(compile(seg[0], "transitions_submit.py", "exec"), ns)
    return ns["submit"]


class EngineGhiBoCap(unittest.TestCase):
    def test_dong_bo_cap_la_he_thong_va_gan_cap(self):
        log = []
        _load_submit(log)("EC Contract Review Request", "EC-CTR-2026-00150", "CONTRACT_REVIEW", "thien.vo@ecentric.vn",
                          skip_level_nos=(4,), skip_reason="Cấp Nhân sự chỉ dành cho hợp đồng lao động.")
        skipped = [(a, k) for a, k in log if a[1] == "Skipped"]
        self.assertEqual(len(skipped), 1)
        args, kw = skipped[0]
        self.assertEqual(args[2], "Administrator")                     # khong phai nguoi gui
        self.assertEqual(args[3], 4)
        self.assertEqual(kw["level_name"], "HR & C&B Review")
        self.assertEqual(kw["comment"], "Cấp Nhân sự chỉ dành cho hợp đồng lao động.")
        self.assertEqual(kw["related_user"], "thien.vo@ecentric.vn")   # van biet phieu cua ai
        submitted = [a for a, k in log if a[1] == "Submitted"]
        self.assertEqual(submitted[0][2], "thien.vo@ecentric.vn")      # dong "Da gui" van la nguoi gui

    def test_khong_bo_cap_thi_khong_co_dong_skipped(self):
        log = []
        _load_submit(log)("EC Contract Review Request", "X", "CONTRACT_REVIEW", "a@ec")
        self.assertFalse([a for a, k in log if a[1] == "Skipped"])

    def test_chi_tiet_tra_level_name(self):
        src = _read("approval_center", "shared", "requests", "query_service.py")
        self.assertIn('"level_no", "level_name", "actor", "action"', src)


if __name__ == "__main__":
    unittest.main()
