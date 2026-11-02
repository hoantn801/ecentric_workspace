# Copyright (c) 2026, eCentric and contributors
"""AI Topup: hoan tat buoc xu ly chi MOT lan.

`features/ai_topup/application/service.complete_fulfillment` chi kiem "dung nguoi" (chu
viec hoac SM) ma khong kiem buoc xu ly con mo. Goi lai endpoint `complete_fulfillment` tren
phieu da Completed (bam dup, retry mang, script) thi:
  * `_upsert_account` chay lai -> ghi de `last_topup_at` / plan cua EC AI Account;
  * thong bao "AI Topup completed" ban lai cho nguoi de nghi + quan ly + nguoi xu ly.
Nut tren giao dien (`_can_complete`) da an o trang thai nay; luat phai nam o server.

Nap MA NGUON THAT cua service voi frappe gia (khong can bench).
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "..", "features", "ai_topup", "application", "service.py")


class _Throw(Exception):
    pass


class _Doc(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def save(self, ignore_permissions=False):
        _calls.append(("save", self.get("name")))


_calls = []


def _load(doc):
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.session = types.SimpleNamespace(user="op@x")
    fr.get_roles = lambda u=None: []

    def _throw(msg, exc=None):
        raise _Throw(msg)
    fr.throw = _throw
    fr.get_doc = lambda dt, name=None: doc
    fr.whitelist = lambda *a, **k: (lambda fn: fn)
    fr.utils = types.SimpleNamespace(now_datetime=lambda: "2026-11-02 10:00:00")
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = fr.utils.now_datetime
    eng = types.ModuleType("transitions_fake")
    eng.close_fulfillment_todos = lambda *a, **k: _calls.append(("close_todos",))
    eng.notify = lambda users, *a, **k: _calls.append(("notify", tuple(users)))
    eng.request_label = lambda *a, **k: "label"
    ur = types.ModuleType("user_rules_fake")
    ur.normalize_email = lambda e: (e or "").strip().lower()
    cs = types.ModuleType("command_service_fake")
    cs.attach_extra_files = lambda *a, **k: None
    wf = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    wf.transitions = eng
    mods = {"frappe": fr, "frappe.utils": utils,
            "ecentric_workspace.approval_center.shared.workflow": wf,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.shared.workflow.user_rules": ur,
            "ecentric_workspace.approval_center.shared.requests.command_service": cs}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        mod = types.ModuleType("_ai_topup_service_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "ai_topup/service.py", "exec"), mod.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    mod._upsert_account = lambda d: _calls.append(("upsert", d.get("name")))
    # complete_fulfillment import command_service ben trong ham -> giu module gia trong luc goi.
    mod._mods = mods
    return mod


def _run(mod, *a, **k):
    saved = {n: sys.modules.get(n) for n in mod._mods}
    sys.modules.update(mod._mods)
    try:
        return mod.complete_fulfillment(*a, **k)
    finally:
        for n, v in saved.items():
            if v is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = v


def _doc(status):
    return _Doc(name="AIT-1", requested_by="req@x", fulfillment_owner="op@x",
                fulfillment_status=status, confirmed_account_manager="mgr@x",
                actual_tax_fee_basis="Included", payment_proof="/private/files/p.pdf",
                invoice_receipt=None, approval_request="AR-1")


class TestHoanTatMotLan(unittest.TestCase):
    def setUp(self):
        del _calls[:]

    def test_phieu_da_completed_khong_hoan_tat_lai(self):
        mod = _load(_doc("Completed"))
        with self.assertRaises(_Throw):
            _run(mod, "AIT-1", user="op@x")
        kinds = [c[0] for c in _calls]
        self.assertNotIn("upsert", kinds, "khong duoc ghi lai EC AI Account")
        self.assertNotIn("notify", kinds, "khong duoc ban lai thong bao hoan tat")

    def test_phieu_chua_vao_buoc_xu_ly_khong_hoan_tat(self):
        mod = _load(_doc(None))
        with self.assertRaises(_Throw):
            _run(mod, "AIT-1", user="op@x")

    def test_doi_chung_dang_xu_ly_thi_hoan_tat_binh_thuong(self):
        doc = _doc("In Progress")
        mod = _load(doc)
        _run(mod, "AIT-1", user="op@x")
        self.assertEqual(doc["fulfillment_status"], "Completed")
        kinds = [c[0] for c in _calls]
        self.assertIn("upsert", kinds)
        self.assertIn("notify", kinds)


if __name__ == "__main__":
    unittest.main()
