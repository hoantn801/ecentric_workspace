# Copyright (c) 2026, eCentric and contributors
"""Hoan tat xu ly chi khi buoc xu ly DANG MO (QA t1, 03/11/2026).

Loi: `complete_fulfillment` cua AI Topup, Asset, Data, Document, System Request chi hoi
"ban co phai chu viec / System Manager khong" - KHONG hoi buoc xu ly con mo khong. Hau qua:
  * chu viec bam lai (hoac goi lai API) tren phieu DA Completed -> ghi de tom tat ket qua,
    nguoi hoan tat, thoi diem hoan tat; bao lai nguoi de nghi - khong mot dong lich su nao;
  * phieu bi quan tri HUY buoc xu ly (cancel_fulfillment) -> chu cu van "Hoan tat" duoc,
    hoi sinh mot viec da huy;
  * System Manager "hoan tat" duoc mot phieu CHUA DUYET / da Tu choi (fulfillment_status rong).
Daily Target, Hiring, Booking da co chot nay - cung mot luat cho moi form.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "features")):
            return root
        root = os.path.dirname(root)
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
FORMS = ("ai_topup", "asset_request", "data_request", "document_request", "system_request")
OWNER = "owner@x"


class _Stop(Exception):
    pass


class _Doc(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def save(self, ignore_permissions=False):
        self["_saved"] = True


def _load(form, doc, roles=()):
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.session = types.SimpleNamespace(user=OWNER)
    fr.get_roles = lambda u=None: list(roles)
    fr.get_doc = lambda dt, name=None: doc
    fr.parse_json = lambda x: x

    def throw(msg, *a, **k):
        raise _Stop(msg)
    fr.throw = throw
    fr.whitelist = lambda *a, **k: (lambda f: f)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: "2026-11-03 10:00:00"
    fr.utils = utils
    eng = types.SimpleNamespace(close_fulfillment_todos=lambda *a, **k: None,
                                notify=lambda *a, **k: None, request_label=lambda *a, **k: "x")
    wf = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    wf.transitions = eng
    ur = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.user_rules")
    ur.normalize_email = lambda e: e
    cs = types.ModuleType("ecentric_workspace.approval_center.shared.requests.command_service")
    cs.attach_extra_files = lambda *a, **k: None
    mods = {"frappe": fr, "frappe.utils": utils,
            "ecentric_workspace.approval_center.shared.workflow": wf,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.shared.workflow.user_rules": ur,
            "ecentric_workspace.approval_center.shared.requests.command_service": cs}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    path = os.path.join(_ROOT, "approval_center", "features", form, "application", "service.py")
    mod = types.ModuleType("_svc_" + form)
    try:
        exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
    except BaseException:
        for k, v in saved.items():
            sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
        raise
    return mod, saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _complete(form, status, roles=()):
    doc = _Doc(name="X-1", doctype="EC X", fulfillment_status=status, fulfillment_owner=OWNER,
               fulfillment_summary="da xong", requested_by="req@x", approval_request="AR-1",
               actual_tax_fee_basis="Included", account_mode="Existing Account")
    mod, saved = _load(form, doc, roles)
    try:
        mod._upsert_account = lambda d: None          # chi AI Topup co; khong lien quan
        try:
            if form == "ai_topup":
                mod.complete_fulfillment("X-1", user=OWNER)
            else:
                mod.complete_fulfillment("X-1", user=OWNER, payload={})
        except _Stop as e:
            return "blocked", str(e), doc
        return "done", None, doc
    finally:
        _restore(saved)


class TestHoanTatChiKhiBuocXuLyDangMo(unittest.TestCase):

    def test_khong_hoan_tat_lai_phieu_da_completed(self):
        for form in FORMS:
            res, _msg, doc = _complete(form, "Completed")
            self.assertEqual(res, "blocked", "%s: ghi de ket qua phieu da hoan tat" % form)
            self.assertFalse(doc.get("_saved"), form)

    def test_khong_hoi_sinh_viec_da_huy(self):
        for form in FORMS:
            self.assertEqual(_complete(form, "Cancelled")[0], "blocked", form)

    def test_system_manager_khong_hoan_tat_phieu_chua_vao_buoc_xu_ly(self):
        for form in FORMS:
            self.assertEqual(_complete(form, None, roles=("System Manager",))[0], "blocked", form)

    def test_doi_chung_dang_xu_ly_thi_hoan_tat_duoc(self):
        for form in FORMS:
            res, msg, doc = _complete(form, "In Progress")
            self.assertEqual(res, "done", "%s: %s" % (form, msg))
            self.assertEqual(doc.fulfillment_status, "Completed", form)


if __name__ == "__main__":
    unittest.main()
