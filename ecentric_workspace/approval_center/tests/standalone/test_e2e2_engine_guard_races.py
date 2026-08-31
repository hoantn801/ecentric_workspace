# Copyright (c) 2026, eCentric and contributors
"""BOT D (2026-09-01) - tai hien HAI lo hong dong thoi cua engine transitions.py.

Ca hai cung mot ho: cac duong DOT BIEN trang thai kiem dieu kien TRUOC khi lay khoa hang
(hoac khong lay khoa), va KHONG kiem lai sau khi khoa ve tay minh. Cua so giua "doc trang
thai" va "ghi trang thai" la noi mot giao dich khac vua commit chen vao.

  LO 1 (approve sau reject): `approve()` doc `req` + `_guard_open` O NGOAI khoa
  (transitions.py:978-980), lay for_update xong KHONG doc lai. Nguoi B bam Duyet trong khi
  nguoi A bam Tu choi: B cho khoa, A commit Rejected, B tinh day - hang approver cua B van
  Pending (reject chi ghi hang cua A) nen B di tiep: ghi "Approved" len hang cua minh + mot
  dong audit "Approved" TREN MOT PHIEU DA BI TU CHOI. `_evaluate` doc trang thai moi nen
  trang thai cuoi van Rejected (khong lat ket qua) - nhung ho so audit tu mau thuan.

  LO 2 (chu ky thang lenh tra lai): `_guard_open` chi chan TERMINAL = (Approved, Rejected,
  Cancelled); "Information Required" KHONG nam trong do. `verify_and_complete` (worker ky
  so) goi `engine.approve` co the cham vai phut sau khi approver bam nut; neu trong khoang
  do mot approver KHAC cung cap da "Yeu cau bo sung", worker van approve duoc: cap dong,
  phieu di tiep / hoan tat trong khi nguoi de nghi tin rang phieu dang dung cho bo sung.
  Doi chieu: `admin_override_current_level` (transitions.py:1165-1166) CO check
  `approval_status == "Pending"` - `approve()` thi khong.

Test CHAY CODE THAT cua transitions.py (nap bang exec voi frappe gia trong sys.modules,
tra lai nguyen trang trong finally - pattern test_sendback_cycle_completes.py). Chi hai
diem noi bat duoc thay the vi can ha tang site: `notify` (notification_center) va
`_signature_guard` (cap trong kich ban khong bat ky so). Toan bo approve / reject /
request_information / _evaluate / decide_level / complete_approval / log_action la that.

Cac assertion o day KHOA HANH VI HIEN TAI (dang sai) de lam bang chung tai hien va de suite
van xanh. Khi va (doc lai req + _guard_open SAU for_update; approve doi approval_status ==
"Pending" nhu admin_override), hai test `test_lo_*` PHAI do - luc do dao assertion sang
`assertRaises` la xong. Test `test_doi_chung_*` la doi chung duong: khoa hien co van chan
dung cac ca da duoc bao ve (khong phai harness "cai gi cung xanh").

Ba bay da ne:
  * stub-tra-moi-truong: moi field seed deu doi chieu JSON DocType (approval_status,
    information_requested_from_level, status "Information Requested"... deu co that);
  * grep-trung-chu-thich: khong grep, chay ham that;
  * throw-sau-ghi: cac kich ban loi khong co throw sau khi ghi (LO 1 ket thuc bang return
    trong _evaluate; LO 2 ket thuc bang complete_approval).
"""
import io
import os
import sys
import types
import unittest
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()

AR = "EC Approval Request"
RL = "EC Approval Request Level"
AP = "EC Approval Request Approver"
ACT = "EC Approval Action"


class _D(dict):
    """Nhu frappe._dict: doc duoc bang ca r["x"] lan r.x."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Doc(object):
    """Ban chieu co thuoc tinh cua mot hang trong store; save() ghi nguoc lai."""

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

    def save(self, ignore_permissions=False):
        self._store[self._doctype][self._row["name"]].update(self._row)


class _ValidationError(Exception):
    pass


class _FrappeStub(object):
    """DB trong bo nho, du cho cac duong approve/reject/request_information.

    Truy van ngoai du kien thi NO TO (raise) thay vi tra rong im lang."""

    def __init__(self):
        self.store = {AR: {}, RL: {}, AP: {}, ACT: {}, "ToDo": {}}
        self.db = self
        self.session = types.SimpleNamespace(user="Administrator")
        self.flags = types.SimpleNamespace(mute_messages=False)
        self.local = types.SimpleNamespace(message_log=[])
        self.ValidationError = _ValidationError
        self.PermissionError = _ValidationError
        self._act_seq = 0
        #: chay MOT LAN ngay khi approve() lay for_update tren EC Approval Request -
        #: mo phong "giao dich khac commit xong trong luc minh cho khoa hang".
        self.on_request_lock = None

    # --- helpers ---------------------------------------------------------- #
    def _match(self, row, filters):
        for k, v in (filters or {}).items():
            if isinstance(v, (list, tuple)):
                op, val = v[0], v[1]
                cur = row.get(k)
                if op == "<":
                    if not (cur is not None and cur < val):
                        return False
                elif op == "in":
                    if cur not in val:
                        return False
                elif op == "!=":
                    if cur == val:
                        return False
                else:
                    raise AssertionError("op filter chua ho tro: %r" % (v,))
            elif row.get(k) != v:
                return False
        return True

    # --- frappe.* --------------------------------------------------------- #
    def throw(self, msg, exc=None):
        raise _ValidationError(msg)

    def get_all(self, doctype, filters=None, fields=None, pluck=None,
                order_by=None, limit_page_length=None, distinct=False, **kw):
        if doctype not in self.store:
            raise AssertionError("khong mong doi get_all %s" % doctype)
        rows = [r for r in self.store[doctype].values() if self._match(r, filters)]
        if order_by and "level_no" in order_by:
            rows.sort(key=lambda r: r.get("level_no") or 0)
        if pluck:
            return [r.get(pluck) for r in rows]
        if fields:
            return [_D({f: r.get(f) for f in fields}) for r in rows]
        return [_D(dict(r)) for r in rows]

    def get_doc(self, doctype_or_dict, name=None):
        if isinstance(doctype_or_dict, dict):
            d = dict(doctype_or_dict)
            dt = d.pop("doctype")
            if dt not in self.store:
                raise AssertionError("khong mong doi insert %s" % dt)
            store, stub = self.store, self

            class _New(object):
                def insert(self, ignore_permissions=False):
                    stub._act_seq += 1
                    d["name"] = "%s-%04d" % (dt.replace(" ", "-"), stub._act_seq)
                    d["_order"] = stub._act_seq          # thu tu ghi, de doi chieu audit
                    store[dt][d["name"]] = d
                    return _Doc(store, dt, d["name"])
            return _New()
        if name not in self.store.get(doctype_or_dict, {}):
            raise AssertionError("get_doc %s %s: khong co" % (doctype_or_dict, name))
        return _Doc(self.store, doctype_or_dict, name)

    # --- frappe.db.* ------------------------------------------------------ #
    def get_value(self, doctype, name, fieldname=None, as_dict=False,
                  for_update=False, order_by=None):
        if for_update and doctype == AR and self.on_request_lock:
            cb, self.on_request_lock = self.on_request_lock, None   # chong de quy
            cb()
        row = self.store.get(doctype, {}).get(name)
        if row is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            out = _D({f: row.get(f) for f in fieldname})
            return out if as_dict else tuple(out.values())
        return row.get(fieldname)

    def set_value(self, doctype, name, field_or_dict, value=None,
                  update_modified=True):
        row = self.store[doctype][name]
        if isinstance(field_or_dict, dict):
            row.update(field_or_dict)
        else:
            row[field_or_dict] = value

    def count(self, doctype, filters=None):
        return len([r for r in self.store.get(doctype, {}).values()
                    if self._match(r, filters)])

    def exists(self, doctype, filters=None):
        if isinstance(filters, str):
            return filters in self.store.get(doctype, {})
        for r in self.store.get(doctype, {}).values():
            if self._match(r, filters):
                return r.get("name", True)
        return None


def _load_engine(stub):
    """Nap transitions.py THAT voi frappe gia; tra lai sys.modules trong finally."""
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime(2026, 9, 1, 10, 0, 0)
    utils.add_to_date = lambda d, **kw: d + timedelta(hours=kw.get("hours", 0))
    utils.getdate = lambda v: v
    stub.utils = utils
    stub._ = lambda s: s
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = stub
    sys.modules["frappe.utils"] = utils
    try:
        with io.open(os.path.join(_ROOT, "approval_center", "shared", "workflow",
                                  "transitions.py"), encoding="utf-8") as fh:
            src = fh.read()
        mod = types.ModuleType("_engine_under_test")
        exec(compile(src, "transitions.py", "exec"), mod.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    # Hai diem noi can ha tang site - thay bang ban ghi nhan, phan con lai giu nguyen.
    mod.notify = lambda users, subject, doctype, name: None
    mod._signature_guard = lambda req, level_no, actor: None   # cap khong bat ky so
    return mod


def _seed(stub, mode):
    """Mot phieu 1 cap, 2 nguoi duyet a@x / b@x, dang In Progress."""
    stub.store[AR]["AR-1"] = {
        "name": "AR-1", "approval_status": "Pending", "current_level": 1,
        "reference_doctype": "EC Payment Request", "reference_name": "PR-1",
        "requested_by": "req@x", "approval_type": "payment_request",
        "information_requested_from_level": 0,
    }
    stub.store[RL]["RL-1"] = {
        "name": "RL-1", "approval_request": "AR-1", "level_no": 1,
        "level_name": "Cap 1", "approval_mode": mode, "minimum_approvals": 0,
        "level_status": "In Progress",
    }
    for suffix, user in (("A", "a@x"), ("B", "b@x")):
        stub.store[AP]["AP-" + suffix] = {
            "name": "AP-" + suffix, "approval_request": "AR-1", "level_no": 1,
            "approver": user, "status": "Pending",
        }


class TestLo1ApproveSauReject(unittest.TestCase):
    """approve() khong doc lai _guard_open sau khi lay khoa hang."""

    def test_lo_approve_ghi_audit_approved_len_phieu_da_rejected(self):
        stub = _FrappeStub()
        _seed(stub, "All Required")
        eng = _load_engine(stub)
        # A commit Tu choi dung luc B dang cho khoa hang (mo phong bang callback trong
        # for_update - y het thu tu that: B doc Pending -> cho khoa -> A commit -> B tiep).
        stub.on_request_lock = lambda: eng.reject("AR-1", actor="a@x", comment="khong duyet")

        # DA VA (31/08): approve() doc lai approval_status SAU khi co khoa hang va
        # _guard_open lan hai. B den sau lenh Tu choi cua A thi phai bi nem, khong duoc
        # ghi mot dong "Approved" len phieu da Rejected.
        with self.assertRaises(_ValidationError) as ctx:
            eng.approve("AR-1", actor="b@x")
        self.assertIn("Rejected", str(ctx.exception))
        # Phieu giu nguyen Rejected, hang cua B khong bi dung toi:
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Rejected")
        self.assertNotEqual(stub.store[AP]["AP-B"]["status"], "Approved",
                            "hang cua B khong duoc thanh Approved tren phieu da Rejected")
        # Va audit KHONG co dong Approved nao sau dong Rejected:
        acts = sorted(stub.store[ACT].values(), key=lambda r: r["_order"])
        seq_actions = [a["action"] for a in acts]
        self.assertIn("Rejected", seq_actions)
        self.assertNotIn("Approved", seq_actions,
                         "audit sach: khong dong Approved nao tren phieu da Rejected")

    def test_doi_chung_khoa_hien_co_chan_dung_ca_any_one(self):
        """Doi chung: Any One, A duyet xong truoc -> hang cua B bi Skipped, B den sau
        bi tu choi dung cach. Chung minh khoa + re-check hang approver DANG lam viec."""
        stub = _FrappeStub()
        _seed(stub, "Any One")
        eng = _load_engine(stub)
        eng.approve("AR-1", actor="a@x")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved")
        self.assertEqual(stub.store[AP]["AP-B"]["status"], "Skipped")
        with self.assertRaises(_ValidationError):
            eng.approve("AR-1", actor="b@x")     # hang cua B khong con Pending -> chan

    def test_doi_chung_double_click_cung_mot_nguoi_bi_chan(self):
        stub = _FrappeStub()
        _seed(stub, "All Required")
        eng = _load_engine(stub)
        eng.approve("AR-1", actor="a@x")
        with self.assertRaises(_ValidationError):
            eng.approve("AR-1", actor="a@x")     # hang da Approved -> khong con Pending


class TestLo2ChuKyThangSendback(unittest.TestCase):
    """DA VA 31/08: approve() chan "Information Required" sau khoa - truoc do worker ky so
    approve de len lenh tra lai cua approver khac."""

    def test_lo_approve_hoan_tat_phieu_dang_information_required(self):
        stub = _FrappeStub()
        _seed(stub, "Any One")
        eng = _load_engine(stub)
        # A tra lai phieu (that, chay code that):
        eng.request_information("AR-1", actor="a@x", comment="bo sung hoa don")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Information Required")
        # Worker ky so cua B (verify_and_complete -> engine.approve voi actor=dsr.approver)
        # ve dich sau do vai giay/phut. HANH VI HIEN TAI: di tuot toi complete_approval.
        # DA VA (31/08): approve() chan "Information Required" - phieu dang bi tra lai
        # thi khong cap nao duoc dong, ke ca khi worker ky so ve dich sau do.
        with self.assertRaises(_ValidationError) as ctx:
            eng.approve("AR-1", actor="b@x")
        self.assertIn("bổ sung", str(ctx.exception))
        # Lenh tra lai cua A con nguyen, khong bi chu ky cua B de mat:
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Information Required")
        self.assertEqual(stub.store[AP]["AP-A"]["status"], "Information Requested")

    def test_doi_chung_terminal_van_bi_chan(self):
        """_guard_open van chan dung TERMINAL - lo hong chi la thieu Information Required."""
        stub = _FrappeStub()
        _seed(stub, "Any One")
        eng = _load_engine(stub)
        stub.store[AR]["AR-1"]["approval_status"] = "Cancelled"
        with self.assertRaises(_ValidationError):
            eng.approve("AR-1", actor="b@x")


if __name__ == "__main__":
    unittest.main()
