# Copyright (c) 2026, eCentric and contributors
"""Engine phai doc trang thai bang LOCKING READ sau khi khoa - khong phai khoa roi doc thuong.

VI SAO (QA t1, 03/11/2026). Cac ham quyet dinh cua `transitions` (approve / reject /
request_information / cancel / resubmit / admin_override) da duoc va o vong BOT D (31/08):
"khoa hang roi DOC LAI trang thai". Nhung cach doc lai la `frappe.db.get_value` THUONG.
Duoi REPEATABLE READ cua MariaDB (mac dinh cua Frappe), lenh thuong doc tu ANH CHUP lap o
lan doc DAU cua giao dich - tuc TRUOC khi cho khoa. Doc lai nhu vay tra ve dung trang thai
CU ma ban va muon loai bo. Chinh `platform/esign/events.current_status` da ghi va sua dung
lop loi nay ngay 08/09 ("Locking read luon tra ban moi nhat da commit, khong phu thuoc
snapshot") - engine duyet thi chua.

Bo test cu (test_e2e2_engine_guard_races) KHONG bat duoc vi kho gia cua no khong co anh
chup: doc thuong cung tra ban moi nhat. O day kho gia MO PHONG MVCC:
  * giao dich B lap anh chup luc bat dau (truoc khi A commit);
  * doc thuong cua B -> anh chup; doc CO KHOA (for_update) -> ban da commit moi nhat;
  * B ghi mot dong -> B thay ban moi nhat cua dong do (dung hanh vi InnoDB).
A chay tron ven trong luc B dang cho khoa (callback `on_request_lock` cua kho gia goc).

Bon kich ban that, deu chay code that cua transitions.py:
  1. All Required, A va B cung bam Duyet -> truoc khi sua: CA HAI deu Approved nhung cap
     KHONG BAO GIO dong (moi ben thay ben kia "Pending" trong anh chup) - phieu ket vinh vien.
     Each Group (New Staff Preparation, bon nhom xac nhan song song) cung mot lop loi.
  2. A Tu choi, B Duyet cung luc -> B ghi "Approved" len phieu da Rejected (lo BOT D cu,
     van con duoi RR).
  3. Any One 2 cap, A va B cung bam -> B ghi de dong Approved cua A thanh Skipped va kich
     hoat cap 2 lan thu hai.
  4. Quan tri "Duyet thay" trong luc nguoi de nghi Huy -> phieu Cancelled bi hoi sinh thanh
     Approved (admin_override khong he doc lai trang thai sau khoa).
"""
import copy
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "_e2e2_base", os.path.join(_HERE, "test_e2e2_engine_guard_races.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

AR, RL, AP, ACT = _base.AR, _base.RL, _base.AP, _base.ACT
_ValidationError = _base._ValidationError


class _MvccStub(_base._FrappeStub):
    """Kho gia co ANH CHUP cho giao dich dang chay (B). None = khong co anh chup."""

    def __init__(self):
        super().__init__()
        self.snap = None
        self.store["DocShare"] = {}

    def log_error(self, *a, **k):
        pass

    # --- giao dich ------------------------------------------------------- #
    def begin_snapshot(self):
        self.snap = copy.deepcopy(self.store)

    def _view(self, for_update=False):
        return self.store if (self.snap is None or for_update) else self.snap

    def _own_write(self, doctype, name):
        """InnoDB: dong minh vua ghi -> doc thuong cua minh thay ban MOI NHAT cua dong do."""
        if self.snap is not None and name in self.store.get(doctype, {}):
            self.snap.setdefault(doctype, {})[name] = copy.deepcopy(self.store[doctype][name])

    # --- doc --------------------------------------------------------------- #
    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None,
                limit_page_length=None, distinct=False, for_update=False, **kw):
        saved, self.store = self.store, self._view(for_update)
        try:
            return super().get_all(doctype, filters=filters, fields=fields, pluck=pluck,
                                   order_by=order_by, limit_page_length=limit_page_length)
        finally:
            self.store = saved

    def get_value(self, doctype, name, fieldname=None, as_dict=False, for_update=False,
                  order_by=None):
        if for_update and doctype == AR and self.on_request_lock:
            cb, self.on_request_lock = self.on_request_lock, None
            snap, self.snap = self.snap, None        # A chay voi goc nhin cua A (ban moi nhat)
            try:
                cb()
            finally:
                self.snap = snap
        saved, self.store = self.store, self._view(for_update)
        try:
            return super().get_value(doctype, name, fieldname, as_dict=as_dict)
        finally:
            self.store = saved

    def count(self, doctype, filters=None):
        saved, self.store = self.store, self._view()
        try:
            return super().count(doctype, filters)
        finally:
            self.store = saved

    def exists(self, doctype, filters=None):
        saved, self.store = self.store, self._view()
        try:
            return super().exists(doctype, filters)
        finally:
            self.store = saved

    def get_doc(self, doctype_or_dict, name=None):
        if isinstance(doctype_or_dict, dict):
            stub = self
            dt = doctype_or_dict.get("doctype")
            inner = super().get_doc(doctype_or_dict)

            class _Ins(object):
                def insert(self, ignore_permissions=False):
                    doc = inner.insert(ignore_permissions)
                    stub._own_write(dt, doc.name)
                    return doc
            return _Ins()
        view = self._view()
        if name not in view.get(doctype_or_dict, {}):
            raise AssertionError("get_doc %s %s: khong co" % (doctype_or_dict, name))
        doc = _base._Doc(view, doctype_or_dict, name)
        stub = self

        def _save(ignore_permissions=False):
            stub.store[doctype_or_dict][name].update(doc._row)
            stub._own_write(doctype_or_dict, name)
        object.__setattr__(doc, "save", _save)
        return doc

    # --- ghi (luon vao ban da commit, roi thay ban moi cua chinh dong do) -- #
    def set_value(self, doctype, name, field_or_dict, value=None, update_modified=True):
        super().set_value(doctype, name, field_or_dict, value, update_modified)
        self._own_write(doctype, name)


def _engine(stub):
    eng = _base._load_engine(stub)
    # Ha tang site khong co trong kho gia - thay bang ham rong, phan con lai la code that.
    eng.assign = lambda *a, **k: None
    eng.close_todos = lambda *a, **k: None
    eng._luong_co_ky_so = lambda req, ctx: False
    eng.activated = []
    real = eng._activate_level

    def _spy(req, level_no):
        eng.activated.append(level_no)
        return real(req, level_no)
    eng._activate_level = _spy
    return eng


def _seed_two_levels(stub, mode1="Any One"):
    stub.store[AR]["AR-1"] = {
        "name": "AR-1", "approval_status": "Pending", "current_level": 1,
        "reference_doctype": "EC Payment Request", "reference_name": "PR-1",
        "requested_by": "req@x", "approval_type": "payment_request",
        "information_requested_from_level": 0,
    }
    for no, mode, st in ((1, mode1, "In Progress"), (2, "Any One", "Pending")):
        stub.store[RL]["RL-%d" % no] = {
            "name": "RL-%d" % no, "approval_request": "AR-1", "level_no": no,
            "level_name": "Cap %d" % no, "approval_mode": mode, "minimum_approvals": 0,
            "level_status": st, "sla_policy": None,
        }
    for key, no, user in (("A", 1, "a@x"), ("B", 1, "b@x"), ("C", 2, "c@x")):
        stub.store[AP]["AP-" + key] = {
            "name": "AP-" + key, "approval_request": "AR-1", "level_no": no,
            "approver": user, "status": "Pending",
        }


def _actions(stub):
    return [a["action"] for a in sorted(stub.store[ACT].values(), key=lambda r: r["_order"])]


class TestDongThoiDuoiRepeatableRead(unittest.TestCase):

    def test_all_required_hai_nguoi_cung_duyet_cap_phai_dong(self):
        stub = _MvccStub()
        _base._seed(stub, "All Required")
        eng = _engine(stub)
        stub.on_request_lock = lambda: eng.approve("AR-1", actor="a@x")
        stub.begin_snapshot()                       # B bat dau truoc khi A commit
        eng.approve("AR-1", actor="b@x")
        stub.snap = None
        self.assertEqual(stub.store[AP]["AP-A"]["status"], "Approved")
        self.assertEqual(stub.store[AP]["AP-B"]["status"], "Approved")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved",
                         "ca hai nguoi da duyet ma phieu van Pending = ket vinh vien")

    def test_each_group_hai_nhom_cung_xac_nhan_cap_phai_dong(self):
        stub = _MvccStub()
        _base._seed(stub, "Each Group")
        stub.store[AP]["AP-A"]["participant_group"] = "HR"
        stub.store[AP]["AP-B"]["participant_group"] = "HOF"
        eng = _engine(stub)
        eng._close_user_todos = lambda *a, **k: None
        stub.on_request_lock = lambda: eng.approve("AR-1", actor="a@x")
        stub.begin_snapshot()
        eng.approve("AR-1", actor="b@x")
        stub.snap = None
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved")

    def test_duyet_sau_tu_choi_bi_chan_duoi_rr(self):
        stub = _MvccStub()
        _base._seed(stub, "All Required")
        eng = _engine(stub)
        stub.on_request_lock = lambda: eng.reject("AR-1", actor="a@x", comment="khong")
        stub.begin_snapshot()
        with self.assertRaises(_ValidationError):
            eng.approve("AR-1", actor="b@x")
        stub.snap = None
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Rejected")
        self.assertNotIn("Approved", _actions(stub))

    def test_any_one_cung_bam_khong_ghi_de_va_khong_kich_hoat_cap2_hai_lan(self):
        stub = _MvccStub()
        _seed_two_levels(stub, "Any One")
        eng = _engine(stub)
        stub.on_request_lock = lambda: eng.approve("AR-1", actor="a@x")
        stub.begin_snapshot()
        with self.assertRaises(_ValidationError):
            eng.approve("AR-1", actor="b@x")    # cap 1 da dong boi A -> B khong con viec
        stub.snap = None
        self.assertEqual(stub.store[AP]["AP-A"]["status"], "Approved",
                         "dong Approved cua A khong duoc bi ghi de thanh Skipped")
        self.assertEqual(stub.store[AP]["AP-B"]["status"], "Skipped")
        self.assertEqual(eng.activated, [2], "cap 2 chi duoc kich hoat MOT lan")

    def test_duyet_thay_khong_hoi_sinh_phieu_vua_huy(self):
        stub = _MvccStub()
        _base._seed(stub, "Any One")
        eng = _engine(stub)
        stub.on_request_lock = lambda: eng.cancel("AR-1", actor="req@x", reason="thoi")
        stub.begin_snapshot()
        with self.assertRaises(_ValidationError):
            eng.admin_override_current_level("AR-1", actor="sm@x", reason="gap")
        stub.snap = None
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Cancelled")
        self.assertNotIn("Approved", _actions(stub))

    def test_duyet_thay_khong_de_len_lenh_tra_lai(self):
        stub = _MvccStub()
        _base._seed(stub, "Any One")
        eng = _engine(stub)
        stub.on_request_lock = lambda: eng.request_information(
            "AR-1", actor="a@x", comment="bo sung")
        stub.begin_snapshot()
        with self.assertRaises(_ValidationError):
            eng.admin_override_current_level("AR-1", actor="sm@x", reason="gap")
        stub.snap = None
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Information Required")

    def test_doi_chung_khong_dua_thi_van_duyet_binh_thuong(self):
        """Doi chung: khong co giao dich chen ngang -> All Required hai nguoi lan luot duyet."""
        stub = _MvccStub()
        _base._seed(stub, "All Required")
        eng = _engine(stub)
        eng.approve("AR-1", actor="a@x")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Pending")
        eng.approve("AR-1", actor="b@x")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved")


if __name__ == "__main__":
    unittest.main()
