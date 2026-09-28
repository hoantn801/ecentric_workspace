"""Che do cap "Each Group" - moi nhom mot nguoi, cac nhom lam song song (28/09/2026).

Dung cho New Staff Preparation: Lead HR / HOF / CnB / Operation cung nhan viec mot luc, moi
ben bam "Da chuan bi" khi xong; ho so xong khi DU cac ben. Test chay CODE THAT cua
transitions.py (exec voi frappe gia) - khuon test_e2e2_engine_guard_races.py.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_each_group_level.py
"""
import io
import json
import os
import sys
import types
import unittest
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))

AR = "EC Approval Request"
RL = "EC Approval Request Level"
AP = "EC Approval Request Approver"
ACT = "EC Approval Action"


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def get(self, k, d=None):
        return dict.get(self, k, d)


class _Doc(object):
    def __init__(self, store, doctype, name):
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_doctype", doctype)
        object.__setattr__(self, "_row", dict(store[doctype][name]))

    def __getattr__(self, k):
        try:
            return self._row[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self._row[k] = v

    def get(self, k, d=None):
        return self._row.get(k, d)

    def save(self, ignore_permissions=False):
        self._store[self._doctype][self._row["name"]].update(self._row)


class _Err(Exception):
    pass


class _Stub(object):
    def __init__(self):
        self.store = {AR: {}, RL: {}, AP: {}, ACT: {}, "ToDo": {}, "Has Role": {}, "User": {}}
        self.db = self
        self.session = types.SimpleNamespace(user="Administrator")
        self.flags = types.SimpleNamespace(mute_messages=False)
        self.local = types.SimpleNamespace(message_log=[])
        self.ValidationError = _Err
        self.PermissionError = _Err
        self.dispatched = []
        self._seq = 0

    def get_attr(self, path):
        self.dispatched.append(path)
        return lambda name: None

    def _match(self, row, filters):
        for k, v in (filters or {}).items():
            if isinstance(v, (list, tuple)):
                op, val = v[0], v[1]
                cur = row.get(k)
                if op == "in" and cur not in val:
                    return False
                if op == "!=" and cur == val:
                    return False
                if op == "like" and not str(cur or "").startswith(str(val).rstrip("%")):
                    return False
            elif row.get(k) != v:
                return False
        return True

    def throw(self, msg, exc=None):
        raise _Err(msg)

    def get_roles(self, user=None):
        return []

    def parse_json(self, s):
        return json.loads(s) if isinstance(s, str) else s

    def as_json(self, o):
        return json.dumps(o)

    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None,
                limit_page_length=None, distinct=False, **kw):
        rows = [r for r in self.store.get(doctype, {}).values() if self._match(r, filters)]
        rows.sort(key=lambda r: (r.get("level_no") or 0, r.get("_order") or 0))
        if pluck:
            return [r.get(pluck) for r in rows]
        if fields:
            return [_D({f: r.get(f) for f in fields}) for r in rows]
        return [_D(dict(r)) for r in rows]

    def get_doc(self, doctype_or_dict, name=None):
        if isinstance(doctype_or_dict, dict):
            d = dict(doctype_or_dict)
            dt = d.pop("doctype")
            store, stub = self.store, self

            class _New(object):
                def insert(self, ignore_permissions=False):
                    stub._seq += 1
                    d["name"] = d.get("name") or "%s-%04d" % (dt.replace(" ", "-"), stub._seq)
                    d["_order"] = stub._seq
                    store.setdefault(dt, {})[d["name"]] = d
                    return _Doc(store, dt, d["name"])
            return _New()
        return _Doc(self.store, doctype_or_dict, name)

    def get_value(self, doctype, name, fieldname=None, as_dict=False, for_update=False, **kw):
        if isinstance(name, dict):
            hit = [r for r in self.store.get(doctype, {}).values() if self._match(r, name)]
            name = hit[0]["name"] if hit else None
        row = self.store.get(doctype, {}).get(name)
        if row is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            out = _D({f: row.get(f) for f in fieldname})
            return out if as_dict else tuple(out.values())
        return row.get(fieldname)

    def set_value(self, doctype, name, field_or_dict, value=None, update_modified=True):
        row = self.store[doctype][name]
        row.update(field_or_dict if isinstance(field_or_dict, dict) else {field_or_dict: value})

    def count(self, doctype, filters=None):
        return len([r for r in self.store.get(doctype, {}).values() if self._match(r, filters)])

    def exists(self, doctype, filters=None):
        if isinstance(filters, str):
            return filters in self.store.get(doctype, {})
        for r in self.store.get(doctype, {}).values():
            if self._match(r, filters):
                return r.get("name", True)
        return None


def _load(stub):
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime(2026, 9, 28, 10, 0, 0)
    utils.add_to_date = lambda d, **kw: d + timedelta(hours=kw.get("hours", 0))
    utils.getdate = lambda v: v
    stub.utils = utils
    stub._ = lambda s: s
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = stub
    sys.modules["frappe.utils"] = utils
    try:
        path = os.path.join(_ROOT, "approval_center", "shared", "workflow", "transitions.py")
        mod = types.ModuleType("_eng_each_group")
        exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    calls = []
    mod.notify = lambda users, subject, doctype, name: calls.append(("notify", tuple(users)))
    mod._signature_guard = lambda req, level_no, actor: None
    mod._sla = lambda: types.SimpleNamespace(
        on_approver_removed=lambda **k: calls.append(("sla_removed", k["user"], k["level_no"])),
        on_approver_acted=lambda **k: calls.append(("sla_acted", k["acted_by"])),
        on_level_closed=lambda **k: calls.append(("sla_closed", k["level_no"])),
        on_level_activated=lambda **k: None)
    return mod, calls


GROUPS = (("Lead HR", ["hr1@x"]), ("HOF", ["hof@x"]), ("CnB", ["cnb1@x", "cnb2@x"]),
          ("Operation", ["op1@x", "op2@x"]))


def _seed(stub, groups=GROUPS, mode="Each Group"):
    stub.store[AR]["AR-1"] = {
        "name": "AR-1", "approval_status": "Pending", "current_level": 1,
        "reference_doctype": "EC New Staff Preparation", "reference_name": "NSP-1",
        "requested_by": "recruiter@x", "approval_type": "NEW_STAFF_PREPARATION",
        "information_requested_from_level": 0}
    stub.store[RL]["RL-1"] = {
        "name": "RL-1", "approval_request": "AR-1", "level_no": 1, "level_name": "Chuẩn bị onboard",
        "approval_mode": mode, "minimum_approvals": 0, "level_status": "In Progress"}
    i = 0
    for g, users in groups:
        for u in users:
            i += 1
            stub.store[AP]["AP-%d" % i] = {
                "name": "AP-%d" % i, "approval_request": "AR-1", "request_level": "RL-1",
                "level_no": 1, "approver": u, "status": "Pending", "participant_group": g,
                "source": "Configured User", "_order": i}
            stub.store["ToDo"]["TD-%d" % i] = {
                "name": "TD-%d" % i, "reference_type": "EC New Staff Preparation",
                "reference_name": "NSP-1", "allocated_to": u, "status": "Open"}


def _st(stub, user):
    return [r["status"] for r in stub.store[AP].values() if r["approver"] == user]


def _todo(stub, user):
    return [r["status"] for r in stub.store["ToDo"].values() if r["allocated_to"] == user]


class TestDecideLevel(unittest.TestCase):
    def setUp(self):
        self.eng, _c = _load(_Stub())

    def test_xong_khi_moi_nhom_co_mot_nguoi(self):
        d = self.eng.decide_level
        self.assertEqual(d("Each Group", 0, ["Approved", "Pending", "Approved"], ["A", "A", "B"]),
                         ("approved", True))
        self.assertEqual(d("Each Group", 0, ["Approved", "Pending"], ["A", "B"]), ("pending", False))
        self.assertEqual(d("Each Group", 0, ["Approved", "Skipped", "Pending"], ["A", "A", "B"]),
                         ("pending", False))
        self.assertEqual(d("Each Group", 0, [], []), ("pending", False))           # cap rong: khong tu xong
        self.assertEqual(d("Each Group", 0, ["Approved"], None), ("pending", False))
        self.assertEqual(d("Each Group", 0, ["Rejected", "Approved"], ["A", "B"]), ("rejected", False))

    def test_che_do_cu_khong_doi(self):
        d = self.eng.decide_level
        self.assertEqual(d("Any One", 0, ["Approved", "Pending"]), ("approved", True))
        self.assertEqual(d("All Required", 0, ["Approved", "Pending"]), ("pending", False))
        self.assertEqual(d("Minimum Count", 2, ["Approved", "Approved", "Pending"]), ("approved", True))


class TestLuongSongSong(unittest.TestCase):
    def setUp(self):
        self.stub = _Stub()
        _seed(self.stub)
        self.eng, self.calls = _load(self.stub)

    def test_mot_nguoi_xac_nhan_la_ca_nhom_xong_con_nhom_khac_van_cho(self):
        self.eng.approve("AR-1", actor="cnb1@x", comment="da mo BHXH")
        s = self.stub
        self.assertEqual(_st(s, "cnb1@x"), ["Approved"])
        self.assertEqual(_st(s, "cnb2@x"), ["Skipped"])
        self.assertEqual(s.store[AR]["AR-1"]["approval_status"], "Pending")      # 3 nhom con lai
        self.assertEqual(s.store[RL]["RL-1"]["level_status"], "In Progress")
        for u in ("hr1@x", "hof@x", "op1@x", "op2@x"):
            self.assertEqual(_st(s, u), ["Pending"], u)
            self.assertEqual(_todo(s, u), ["Open"], u)
        self.assertEqual(_todo(s, "cnb1@x"), ["Closed"])       # xong phan minh -> ToDo dong ngay
        self.assertEqual(_todo(s, "cnb2@x"), ["Cancelled"])    # het viec -> huy
        self.assertIn(("sla_removed", "cnb2@x", 1), self.calls)
        self.assertNotIn(("sla_removed", "cnb1@x", 1), self.calls)
        skipped = [a for a in s.store[ACT].values() if a["action"] == "Skipped"]
        self.assertEqual([a["related_user"] for a in skipped], ["cnb2@x"])
        self.assertIn("CnB", skipped[0]["comment"])

    def test_du_bon_nhom_thi_hoan_tat(self):
        for u in ("op2@x", "hof@x", "cnb2@x"):
            self.eng.approve("AR-1", actor=u)
        self.assertEqual(self.stub.store[AR]["AR-1"]["approval_status"], "Pending")
        self.eng.approve("AR-1", actor="hr1@x")
        s = self.stub
        self.assertEqual(s.store[AR]["AR-1"]["approval_status"], "Approved")
        self.assertEqual(s.store[RL]["RL-1"]["level_status"], "Approved")
        self.assertEqual(_st(s, "op1@x"), ["Skipped"])
        self.assertEqual(_st(s, "cnb1@x"), ["Skipped"])

    def test_nguoi_cung_nhom_da_xong_khong_bam_duoc_nua(self):
        self.eng.approve("AR-1", actor="op1@x")
        with self.assertRaises(_Err):
            self.eng.approve("AR-1", actor="op2@x")

    def test_khong_co_tu_choi(self):
        with self.assertRaises(_Err) as ctx:
            self.eng.reject("AR-1", actor="hof@x", comment="khong")
        self.assertIn("Yêu cầu bổ sung", str(ctx.exception))
        self.assertEqual(_st(self.stub, "hof@x"), ["Pending"])
        self.assertEqual(self.stub.store[AR]["AR-1"]["approval_status"], "Pending")


class TestMotNguoiHaiNhom(unittest.TestCase):
    def test_bam_mot_lan_xac_nhan_ca_hai_nhom(self):
        stub = _Stub()
        _seed(stub, (("Lead HR", ["tuan@x"]), ("CnB", ["tuan@x", "cnb@x"]), ("HOF", ["hof@x"])))
        eng, calls = _load(stub)
        eng.approve("AR-1", actor="tuan@x")
        self.assertEqual(_st(stub, "tuan@x"), ["Approved", "Approved"])
        self.assertEqual(_st(stub, "cnb@x"), ["Skipped"])
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Pending")   # con HOF
        eng.approve("AR-1", actor="hof@x")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved")

    def test_cap_thuong_van_mot_dong_mot_lan(self):
        """Any One khong dung toi vong lap nhieu dong - hanh vi cu giu nguyen."""
        stub = _Stub()
        _seed(stub, (("", ["a@x", "b@x"]),), mode="Any One")
        eng, _c = _load(stub)
        eng.approve("AR-1", actor="a@x")
        self.assertEqual(_st(stub, "b@x"), ["Skipped"])
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved")


class TestDungLuong(unittest.TestCase):
    def _lvl(self, parts):
        return _D(level_no=1, level_name="Chuẩn bị onboard", approval_mode="Each Group",
                  participants=[_D(participant_purpose="Approver", sort_order=i, group_label=g,
                                   source_type="Role", role=r) for i, (g, r) in enumerate(parts)])

    def test_moi_dong_mot_nhom_va_khong_gop_trung(self):
        eng, _c = _load(_Stub())
        members = {"R1": [("x@x", "Role: R1")], "R2": [("x@x", "Role: R2"), ("y@x", "Role: R2")]}
        eng.resolve_participants = lambda ps, req, context=None: members[ps[0].role]
        out = eng._resolve_groups(self._lvl([("Lead HR", "R1"), ("CnB", "R2")]), "req@x", {})
        self.assertEqual(out, [("Lead HR", [("x@x", "Role: R1")]),
                               ("CnB", [("x@x", "Role: R2"), ("y@x", "Role: R2")])])

    def test_nhom_rong_thi_chan_gui(self):
        eng, _c = _load(_Stub())
        eng.resolve_participants = lambda ps, req, context=None: [] if ps[0].role == "R2" else [("x@x", "l")]
        with self.assertRaises(_Err) as ctx:
            eng._resolve_groups(self._lvl([("HOF", "R1"), ("Operation", "R2")]), "req@x", {})
        self.assertIn("Operation", str(ctx.exception))

    def test_ten_nhom_mac_dinh_va_trung_ten(self):
        eng, _c = _load(_Stub())
        eng.resolve_participants = lambda ps, req, context=None: [("u%s@x" % ps[0].role, "l")]
        out = eng._resolve_groups(self._lvl([("", "1"), ("A", "2"), ("A", "3")]), "req@x", {})
        self.assertEqual([g for g, _m in out], ["Nhóm 1", "A", "A (3)"])

    def test_build_snapshot_ghi_nhom_len_tung_dong(self):
        stub = _Stub()
        stub.store[AR]["AR-9"] = {"name": "AR-9", "reference_doctype": "X", "reference_name": "Y"}
        eng, _c = _load(stub)
        eng.resolve_participants = lambda ps, req, context=None: (
            [("a@x", "Role: A")] if ps[0].role == "A" else [("b@x", "Role: B"), ("c@x", "Role: B")])
        eng._skip_earlier_duplicate_levels = lambda req: None
        eng.grant_read_to_snapshot_approvers = lambda req: None
        lvl = self._lvl([("HOF", "A"), ("Operation", "B")])
        lvl.update(name="LVL", minimum_approvals=0, mandatory=1, sla_policy=None,
                   allows_amount_adjustment=0)
        eng.build_snapshot(_D(name="AR-9", reference_doctype="X", reference_name="Y"), None, [lvl], "r@x")
        got = sorted((r["approver"], r["participant_group"]) for r in stub.store[AP].values())
        self.assertEqual(got, [("a@x", "HOF"), ("b@x", "Operation"), ("c@x", "Operation")])


class TestNutTuChoi(unittest.TestCase):
    def test_capabilities_an_tu_choi_o_cap_each_group(self):
        path = os.path.join(_ROOT, "approval_center", "shared", "requests", "capabilities.py")
        src = io.open(path, encoding="utf-8").read()
        self.assertIn('"can_reject": can_act and not _each_group_level(approval_request)', src)
        self.assertIn('== "Each Group"', src)


if __name__ == "__main__":
    unittest.main()
