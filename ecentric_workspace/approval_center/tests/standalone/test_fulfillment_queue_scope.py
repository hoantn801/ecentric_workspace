# Copyright (c) 2026, eCentric and contributors
"""Hang doi xu ly (list_fulfillment_queue) KHONG duoc mo ca loai phieu cho nguoi chi giu MOT
ToDo (QA t1, 03/11/2026).

Loi: `fulfillment_service.list_queue` (8 form dung bind_fulfillment) va ban rieng cua AI
Topup gac cong bang `is_eligible_fulfiller(user, type, doctype)` KHONG truyen ten phieu. O
dang do ham van con duong "co MOT ToDo mo BAT KY tren LOAI phieu nay" - ma ToDo DUYET cung
nam tren chinh DocType nghiep vu (engine.assign). Nen mot truong phong dang co dung mot De
nghi thanh toan cho duyet goi thang endpoint la doc duoc toan bo hang doi Finance cua cong ty:
nguoi thu huong, so tien, ngay chi (payee_full_name, payment_amount...). Day dung la lo hong
ma docstring `is_eligible_fulfiller` noi da "siet 01/09" - con sot o hang doi, giong het
cho `reporting/queries.py` da phai va 16/09.

Luat sau khi sua (khong doi gi voi nguoi xu ly that):
  * System Manager / Fulfiller DUOC CAU HINH tren quy trinh Active -> ca hang doi nhu cu;
  * nguoi khac -> chi nhung phieu ho DANG GIU ToDo mo (vd viec giao dich danh), va muc
    "cua toi" (fulfillment_owner = ho) - khong bao gio thay phieu cua nguoi khac.
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
_PERM = os.path.join(_ROOT, "approval_center", "shared", "workflow", "permissions.py")
_SVC = os.path.join(_ROOT, "approval_center", "shared", "requests", "fulfillment_service.py")
BIZ = "EC Payment Request"
FIN, HEAD, NAMED, SM = "fin@x", "head@x", "named@x", "sm@x"


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _match(row, filters):
    for k, v in (filters or {}).items():
        if isinstance(v, (list, tuple)):
            op, val = v[0], v[1]
            cur = row.get(k)
            if op == "in" and cur not in val:
                return False
            if op == "!=" and cur == val:
                return False
            if op == "is" and val == "set" and not cur:
                return False
        elif row.get(k) != v:
            return False
    return True


def _frappe(user, store, roles):
    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user=user)
    fr._ = lambda s: s
    fr.get_roles = lambda u=None: list(roles.get(u or user, ()))
    fr.queries = []

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None,
                limit_page_length=None, **kw):
        if dt == BIZ:
            fr.queries.append(dict(filters or {}))
        rows = [r for r in store.get(dt, {}).values() if _match(r, filters)]
        if pluck:
            return [r.get(pluck) for r in rows]
        return [_D({f: r.get(f) for f in (fields or r.keys())}) for r in rows]

    def exists(dt, filters=None):
        if isinstance(filters, str):
            return filters in store.get(dt, {})
        return any(_match(r, filters) for r in store.get(dt, {}).values())

    fr.get_all = get_all
    fr.get_list = get_all
    fr.db = types.SimpleNamespace(exists=exists, get_value=lambda *a, **k: None)
    fr.throw = lambda m, *a, **k: (_ for _ in ()).throw(RuntimeError(m))
    fr.PermissionError = RuntimeError
    fr.flags = types.SimpleNamespace(mute_messages=False)
    fr.local = types.SimpleNamespace(message_log=[])
    return fr


def _load(user, store, roles):
    fr = _frappe(user, store, roles)
    names = ("frappe", "ecentric_workspace.approval_center.shared.workflow.transitions",
             "ecentric_workspace.approval_center.shared.workflow.permissions")
    saved = {k: sys.modules.get(k) for k in names}
    try:
        sys.modules["frappe"] = fr
        perm = types.ModuleType("_perm_q")
        exec(compile(io.open(_PERM, encoding="utf-8").read(), _PERM, "exec"), perm.__dict__)
        sys.modules[names[2]] = perm
        sys.modules[names[1]] = types.ModuleType("_tr_q")
        svc = types.ModuleType("_svc_q")
        exec(compile(io.open(_SVC, encoding="utf-8").read(), _SVC, "exec"), svc.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return svc, fr


def _store():
    st = {
        "EC Approval Process": {"P1": {"name": "P1", "approval_type": "PAYMENT_REQUEST",
                                       "status": "Active"}},
        "EC Approval Participant": {"F1": {"name": "F1", "parent": "P1",
                                           "parenttype": "EC Approval Process",
                                           "participant_purpose": "Fulfiller",
                                           "source_type": "Role", "role": "EC Finance"}},
        "ToDo": {
            # ToDo DUYET cua truong phong tren MOT phieu cua nhan vien minh (chua duyet xong).
            "T1": {"name": "T1", "reference_type": BIZ, "reference_name": "PR-9",
                   "allocated_to": HEAD, "status": "Open"},
            # Viec giao DICH DANH cho mot nguoi khong thuoc role xu ly.
            "T2": {"name": "T2", "reference_type": BIZ, "reference_name": "PR-2",
                   "allocated_to": NAMED, "status": "Open"},
        },
        BIZ: {},
    }
    for n in ("PR-1", "PR-2", "PR-3"):
        st[BIZ][n] = {"name": n, "payee_full_name": "Nguoi nhan " + n, "payment_amount": 1e8,
                      "fulfillment_status": "Assigned", "fulfillment_owner": None}
    st[BIZ]["PR-9"] = {"name": "PR-9", "payee_full_name": "x", "payment_amount": 1,
                       "fulfillment_status": None, "fulfillment_owner": None}
    st[BIZ]["PR-4"] = {"name": "PR-4", "payee_full_name": "y", "payment_amount": 2,
                       "fulfillment_status": "In Progress", "fulfillment_owner": FIN}
    return st


ROLES = {FIN: {"EC Finance"}, SM: {"System Manager"}, HEAD: set(), NAMED: set()}
FIELDS = ("name", "payee_full_name", "payment_amount", "fulfillment_status", "fulfillment_owner")


class _Def:
    code = "PAYMENT_REQUEST"
    business_doctype = BIZ


def _q(user, section="unclaimed"):
    svc, _fr = _load(user, _store(), ROLES)
    return sorted(r["name"] for r in svc.list_queue(_Def(), section, FIELDS, "name asc")["rows"])


class TestHangDoiXuLyKhongLoChoNguoiGiuMotToDo(unittest.TestCase):

    def test_truong_phong_co_mot_todo_duyet_khong_thay_hang_doi_finance(self):
        self.assertEqual(_q(HEAD, "unclaimed"), [],
                         "mot ToDo duyet tren PR-9 khong duoc mo ca hang doi thanh toan")
        self.assertEqual(_q(HEAD, "others"), [])

    def test_nguoi_giu_viec_dich_danh_chi_thay_dung_phieu_do(self):
        self.assertEqual(_q(NAMED, "unclaimed"), ["PR-2"])

    def test_fulfiller_cau_hinh_va_system_manager_van_thay_ca_hang_doi(self):
        self.assertEqual(_q(FIN, "unclaimed"), ["PR-1", "PR-2", "PR-3"])
        self.assertEqual(_q(SM, "unclaimed"), ["PR-1", "PR-2", "PR-3"])
        self.assertEqual(_q(SM, "others"), ["PR-4"])
        self.assertEqual(_q(FIN, "mine"), ["PR-4"])

    def test_nguoi_ngoai_khong_co_gi(self):
        self.assertEqual(_q("nobody@x", "unclaimed"), [])


class TestAiTopupDungChungLuat(unittest.TestCase):
    def test_ai_topup_hang_doi_rieng_cung_ap_pham_vi(self):
        src = io.open(os.path.join(_ROOT, "approval_center", "features", "ai_topup",
                                   "controllers", "api.py"), encoding="utf-8").read()
        i = src.index("def list_fulfillment_queue(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn("queue_scope(", body,
                      "AI Topup co hang doi rieng - phai dung CUNG pham vi voi 8 form kia")


if __name__ == "__main__":
    unittest.main()
