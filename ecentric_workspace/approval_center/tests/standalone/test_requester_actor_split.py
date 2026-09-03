# Copyright (c) 2026, eCentric and contributors
"""Chan nguoi trinh: `userId` = tai khoan tich hop (nguoi giu task), chu ky = cua nguoi trinh.

04/09/2026, ba phieu cua chi Hien (00046/00047/00048) deu chet o buoc Trinh ky:
`transition` 400 "khong co quyen... task da duoc xu ly", `bulk-process` 2xx roi 0 chu ky.
Ly do: eContract giao buoc dau cho tai khoan TAO tai lieu = tai khoan tich hop, va gan vai
tro cho node cung khong doi duoc. Nhung 12 chan duyet da ky bang token tich hop voi userId
cua nguoi khac - SCTS tach token khoi nguoi thuc hien. Nen thu tach tiep: userId = nguoi
giu task, signatureInfo = chu ky + HSM cua nguoi trinh.

Ba lop, moi lop mot kiem:
  1. adapter (code THAT cua providers/scts.py, frappe gia): userId di theo actor, signerId
     va viec tra cuu chu ky di theo nguoi trinh. Khong actor -> y het cu.
  2. next_handler.requester_actor (code THAT): chi stage requester, chi khi khac nguoi,
     tat duoc bang cau hinh, khong co mapping thi None chu khong bia.
  3. tasks.py (AST): loi goi transition_with_recipients mang keyword actor_user_id, va gia
     tri do den tu next_handler.requester_actor - khong phai bien nao khac.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

HIEN = "541f8e96-0000-0000-0000-00000000hien"
HOAN = "73f72e15-4f56-4bde-84e9-68edd9918d7c"
SIG_HIEN = "e5407f7e-0000-0000-0000-0000000sighn"
HSM_HIEN = "hsm-cua-hien"
INST = "62fdef3c-e702-48ff-a8cb-8fcce4af61fa"
CFG = {"transition_id": "-2", "transition_name": "Trinh ky",
       "process_action": "WfFunctionRunSignedOther", "sign_type": "ky-tham-gia"}


def _read(rel):
    with io.open(os.path.join(_ESIGN, rel), encoding="utf-8") as fh:
        return fh.read()


def _fake_frappe(conf=None):
    fk = types.ModuleType("frappe")
    fk.conf = dict(conf or {})
    fk._ = lambda s: s
    utils = types.ModuleType("frappe.utils")
    utils.add_to_date = lambda *a, **k: None
    utils.get_datetime = lambda v: v
    utils.now_datetime = lambda: None
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: None
    utils.password = pw
    fk.utils = utils
    return fk, {"frappe": fk, "frappe.utils": utils, "frappe.utils.password": pw}


def _with_fake_frappe(mods, fn):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _load_module(rel, name, mods):
    """Nap bang exec(compile(text)) - KHONG qua .pyc (bai hoc 01/09: __pycache__ vo hieu
    hoa kiem-thu-dot-bien)."""
    def go():
        # scts.py import base + scts_client qua package that; xoa ban cache de doc lai nguon
        for k in list(sys.modules):
            if k.startswith("ecentric_workspace.platform.esign"):
                sys.modules.pop(k)
        mod = types.ModuleType(name)
        mod.__file__ = os.path.join(_ESIGN, rel)
        exec(compile(_read(rel), rel, "exec"), mod.__dict__)
        return mod
    return _with_fake_frappe(mods, go)


# ---------------------------------------------------------------------------- lop 1: adapter
class _FakeClient(object):
    def __init__(self):
        self.calls = []

    def transition(self, instance_id, user_id, to_users, transition_id, transition_name,
                   process_action, sign_type, signature_id, signature_name, comment, token,
                   signature_image=None, signature_extra=None):
        self.calls.append({"instance_id": instance_id, "user_id": user_id,
                           "to_users": list(to_users), "signature_id": signature_id,
                           "signature_extra": dict(signature_extra or {})})
        return {"bulkJobTransactionId": "txn-1"}


def _adapter():
    fk, mods = _fake_frappe()
    scts = _load_module("providers/scts.py", "_scts_under_test", mods)
    a = scts.SctsAdapter.__new__(scts.SctsAdapter)     # bo qua __init__ (netguard, client)
    a._client = _FakeClient()
    a._with_auth = lambda fn: fn("tok")
    a.lookups = []

    def signature_record(user_id, signature_id):
        a.lookups.append((user_id, signature_id))
        return {"id": signature_id, "signerId": HIEN, "hsmCertId": HSM_HIEN,
                "companyId": "ECENTRIC", "name": "Ky tham gia", "base64Image": "img"}
    a.signature_record = signature_record
    return a


class TestAdapterTachActorKhoiNguoiKy(unittest.TestCase):
    def test_co_actor_userId_la_actor_nhung_chu_ky_va_signerId_la_nguoi_trinh(self):
        a = _adapter()
        res = a.transition_with_recipients(INST, HIEN, [HOAN], CFG, SIG_HIEN,
                                           actor_user_id=HOAN)
        self.assertEqual(res, {"bulk_job_transaction_id": "txn-1"})
        c = a._client.calls[-1]
        self.assertEqual(c["user_id"], HOAN, "userId phai la nguoi giu task")
        self.assertEqual(c["signature_id"], SIG_HIEN)
        self.assertEqual(c["signature_extra"]["signerId"], HIEN, "signerId phai la nguoi trinh")
        self.assertEqual(c["signature_extra"]["hsmId"], HSM_HIEN, "chung thu cua nguoi trinh")
        self.assertEqual(a.lookups, [(HIEN, SIG_HIEN)],
                         "tra cuu chu ky theo CHU chu ky, khong theo actor")

    def test_khong_actor_thi_y_het_cu(self):
        a = _adapter()
        a.transition_with_recipients(INST, HIEN, [HOAN], CFG, SIG_HIEN)
        c = a._client.calls[-1]
        self.assertEqual(c["user_id"], HIEN)
        self.assertEqual(c["signature_extra"]["signerId"], HIEN)

    def test_actor_rong_coi_nhu_khong_co(self):
        a = _adapter()
        a.transition_with_recipients(INST, HIEN, [HOAN], CFG, SIG_HIEN, actor_user_id="")
        self.assertEqual(a._client.calls[-1]["user_id"], HIEN)


# ------------------------------------------------------------------- lop 2: next_handler
def _next_handler(conf=None, mapping=None):
    fk, mods = _fake_frappe(conf)
    perms = types.ModuleType("ecentric_workspace.platform.esign.permissions")
    perms.calls = []

    def verified_mapping(user, env):
        perms.calls.append((user, env))
        return mapping
    perms.verified_mapping = verified_mapping
    mods = dict(mods)
    mods["ecentric_workspace.platform.esign.permissions"] = perms
    nh = _load_module("next_handler.py", "_next_handler_under_test", mods)
    # requester_actor import permissions luc GOI, nen giu stub trong sys.modules khi goi
    nh._mods = mods
    nh._perms = perms
    return nh


def _call(nh, fn, *a, **k):
    return _with_fake_frappe(nh._mods, lambda: fn(*a, **k))


SETTINGS = {"username": "hoan.tran@ecentric.vn", "environment": "UAT"}


class TestRequesterActor(unittest.TestCase):
    def test_stage_requester_khac_nguoi_tra_tai_khoan_tich_hop(self):
        nh = _next_handler(mapping={"scts_user_id": HOAN})
        got = _call(nh, nh.requester_actor, {"effective_scts_user_id": HIEN}, SETTINGS,
                    "requester")
        self.assertEqual(got, HOAN)
        self.assertEqual(nh._perms.calls, [("hoan.tran@ecentric.vn", "UAT")],
                         "mapping phai tra theo username + environment cua Provider Settings")

    def test_cung_mot_nguoi_thi_None_de_payload_y_het_cu(self):
        nh = _next_handler(mapping={"scts_user_id": HOAN})
        self.assertIsNone(_call(nh, nh.requester_actor, {"effective_scts_user_id": HOAN},
                                SETTINGS, "requester"))

    def test_stage_approval_khong_bao_gio_tach(self):
        nh = _next_handler(mapping={"scts_user_id": HOAN})
        self.assertIsNone(_call(nh, nh.requester_actor, {"effective_scts_user_id": HIEN},
                                SETTINGS, "approval"))
        self.assertEqual(nh._perms.calls, [], "khong duoc dong toi mapping o stage duyet")

    def test_tat_bang_cau_hinh(self):
        nh = _next_handler(conf={"ec_esign_requester_actor_split": "0"},
                           mapping={"scts_user_id": HOAN})
        self.assertIsNone(_call(nh, nh.requester_actor, {"effective_scts_user_id": HIEN},
                                SETTINGS, "requester"))

    def test_khong_co_mapping_thi_None_khong_bia(self):
        nh = _next_handler(mapping=None)
        self.assertIsNone(_call(nh, nh.requester_actor, {"effective_scts_user_id": HIEN},
                                SETTINGS, "requester"))

    def test_thieu_username_thi_None(self):
        nh = _next_handler(mapping={"scts_user_id": HOAN})
        self.assertIsNone(_call(nh, nh.requester_actor, {"effective_scts_user_id": HIEN},
                                {"environment": "UAT"}, "requester"))
        self.assertEqual(nh._perms.calls, [])


# --------------------------------------------------------------------------- lop 3: tasks.py
class TestTasksDayDung(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(_read("tasks.py"))

    def _calls(self, attr):
        return [n for n in ast.walk(self.tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == attr]

    def test_transition_with_recipients_mang_actor_user_id_tu_requester_actor(self):
        calls = self._calls("transition_with_recipients")
        self.assertEqual(len(calls), 1, "dung mot loi goi de kiem")
        kws = {k.arg: k.value for k in calls[0].keywords}
        self.assertIn("actor_user_id", kws)
        self.assertIsInstance(kws["actor_user_id"], ast.Name)
        var = kws["actor_user_id"].id
        # bien do phai duoc gan tu next_handler.requester_actor(...) - khong phai tu
        # effective_scts_user_id hay hang so nao khac
        srcs = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == var for t in n.targets):
                srcs.append(ast.unparse(n.value))
        self.assertTrue(any("requester_actor(" in s for s in srcs),
                        "actor_user_id phai den tu next_handler.requester_actor; thay: %r" % srcs)

    def test_approve_and_sign_pool_khong_bi_doi(self):
        """Duong pool giu nguyen userId = nguoi ky. Mot bien so moi lan thu."""
        calls = self._calls("approve_and_sign")
        self.assertTrue(calls)
        for c in calls:
            self.assertNotIn("actor_user_id", [k.arg for k in c.keywords])


if __name__ == "__main__":
    unittest.main()
