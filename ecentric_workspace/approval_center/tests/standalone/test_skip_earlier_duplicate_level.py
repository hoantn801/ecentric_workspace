# Copyright (c) 2026, eCentric and contributors
"""Mot nguoi o NHIEU cap duyet -> bo cac cap TRUOC, giu cap CUOI (Hoan chot 09/09).

EC-HIRE-2026-00003: nguoi de nghi la hoan.tran, quan ly truc tiep la anh Lam, ma anh Lam
cung la CEO -> luong co ca "Direct Manager Review" (cap 2) lan "CEO Review" (cap 4) deu tro
ve mot nguoi.

Engine truoc do da bo cap SAU (`_auto_skip_duplicate_level`, chay luc kich hoat). Doi sang bo
cap TRUOC vi hai ly do: tham quyen cao nhat phai nam o CUOI (CEO chot sau khi HR review, khong
phai truoc), va so sach phai ghi CEO duyet o o "CEO Review" chu khong phai o "Direct Manager
Review". Quyet dinh chay luc DUNG LUONG nen thanh tien trinh hien dung ngay tu luc gui.

Bo test giu sau dieu, moi dieu la mot cach hong that:
  1. Trung nguoi -> bo cap truoc, GIU cap sau.
  2. Cap cuoi cua moi nguoi khong bao gio bi bo -> khong the bo sach ca luong.
  3. Cap con nguoi duyet KHAC khong trung -> khong duoc bo (Any-One/All deu an toan).
  4. Cap `mandatory` -> khong duoc bo.
  5. Ba cap cung mot nguoi -> chi con cap cuoi.
  6. `_activate_level` gap cap da Skipped thi di thang, khong dung ToDo/SLA.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "shared")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_TRANS = os.path.join(_root(), "approval_center", "shared", "workflow", "transitions.py")


def _func_source(name):
    src = io.open(_TRANS, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong thay ham %s" % name)


class _DB(object):
    def __init__(self, levels, approvers):
        self.levels = [dict(l) for l in levels]
        self.approvers = [dict(a) for a in approvers]
        self.writes = []

    def set_value(self, dt, name, values, *a, **k):
        self.writes.append((dt, name, dict(values) if isinstance(values, dict) else values))
        pool = self.levels if dt.endswith("Level") else self.approvers
        for row in pool:
            if row.get("name") == name and isinstance(values, dict):
                row.update(values)


def _run_skip(levels, approvers):
    db = _DB(levels, approvers)
    frappe = types.ModuleType("frappe")
    frappe.db = db

    def get_all(dt, filters=None, fields=None, order_by=None, **kw):
        if dt.endswith("Level"):
            return sorted((dict(r) for r in db.levels), key=lambda r: r["level_no"])
        return [dict(r) for r in db.approvers]

    frappe.get_all = get_all
    logs = []
    ns = {
        "frappe": frappe,
        "now_datetime": lambda: "NOW",
        "log_action": lambda *a, **k: logs.append((a, k)),
        "_": lambda s: s,
    }
    exec(compile(_func_source("_skip_earlier_duplicate_levels"), "<skip>", "exec"), ns)
    ns["_skip_earlier_duplicate_levels"](types.SimpleNamespace(name="REQ-1"))
    return db, logs


def _lv(no, name=None, mandatory=0):
    return {"name": "RL-%d" % no, "level_no": no,
            "level_name": name or ("L%d" % no), "mandatory": mandatory,
            "level_status": "Pending"}


def _ap(no, user):
    return {"name": "AP-%d-%s" % (no, user), "level_no": no, "approver": user,
            "status": "Pending"}


def _status(db):
    return {l["level_no"]: l["level_status"] for l in db.levels}


class TestBoCapTruocGiuCapSau(unittest.TestCase):
    def test_ca_hire_00003_bo_cap_2_giu_cap_4(self):
        db, logs = _run_skip(
            [_lv(1, "Da gui"), _lv(2, "Direct Manager"), _lv(3, "HR"), _lv(4, "CEO")],
            [_ap(1, "hoan@x"), _ap(2, "lam@x"), _ap(3, "hr@x"), _ap(4, "lam@x")])
        self.assertEqual(_status(db)[2], "Skipped", "cap Direct Manager phai bi bo")
        self.assertEqual(_status(db)[4], "Pending", "cap CEO phai GIU")
        self.assertEqual(_status(db)[3], "Pending", "cap HR khong lien quan, phai giu")
        self.assertTrue(logs, "phai ghi audit cho tung nguoi bi bo")

    def test_cap_cuoi_cua_moi_nguoi_khong_bao_gio_bi_bo(self):
        db, _l = _run_skip([_lv(1), _lv(2)], [_ap(1, "a@x"), _ap(2, "a@x")])
        self.assertEqual(_status(db)[2], "Pending",
                         "bo ca hai thi khong con ai duyet - khong duoc phep")

    def test_ba_cap_cung_mot_nguoi_chi_con_cap_cuoi(self):
        db, _l = _run_skip([_lv(1), _lv(2), _lv(3)],
                           [_ap(1, "a@x"), _ap(2, "a@x"), _ap(3, "a@x")])
        self.assertEqual(_status(db), {1: "Skipped", 2: "Skipped", 3: "Pending"})


class TestKhongDuocBoNham(unittest.TestCase):
    def test_con_nguoi_duyet_khac_khong_trung_thi_giu_ca_cap(self):
        """Cap 2 co lam@x (trung cap 4) VA hr@x (khong trung) -> hr@x van phai bam."""
        db, _l = _run_skip([_lv(1), _lv(2), _lv(4)],
                           [_ap(1, "req@x"), _ap(2, "lam@x"), _ap(2, "hr@x"), _ap(4, "lam@x")])
        self.assertEqual(_status(db)[2], "Pending")

    def test_cap_mandatory_khong_duoc_bo(self):
        db, _l = _run_skip([_lv(1), _lv(2, mandatory=1), _lv(4)],
                           [_ap(1, "req@x"), _ap(2, "lam@x"), _ap(4, "lam@x")])
        self.assertEqual(_status(db)[2], "Pending",
                         "mandatory da ghi ro trong cau hinh la khong duoc bo")

    def test_khong_trung_ai_thi_khong_dong_gi(self):
        db, logs = _run_skip([_lv(1), _lv(2)], [_ap(1, "a@x"), _ap(2, "b@x")])
        self.assertEqual(_status(db), {1: "Pending", 2: "Pending"})
        self.assertEqual(db.writes, [])
        self.assertEqual(logs, [])

    def test_mot_cap_duy_nhat_thi_khong_dong_gi(self):
        db, _l = _run_skip([_lv(1)], [_ap(1, "a@x")])
        self.assertEqual(db.writes, [])


class TestKichHoatBoQuaCapDaSkipped(unittest.TestCase):
    """`_activate_level` phai di thang qua cap da Skipped - khong ToDo, khong SLA."""

    def _run_activate(self, skipped):
        called = {"advance": [], "past_guard": False}
        ns = {
            "_is_level_skipped": lambda rn, no: skipped,
            "_advance_past_level": lambda req, no: called["advance"].append(no),
        }

        def _rl_for(rn, no):
            called["past_guard"] = True
            raise RuntimeError("DUNG-SAU-CHAN")

        ns["_rl_for"] = _rl_for
        exec(compile(_func_source("_activate_level"), "<act>", "exec"), ns)
        # cac ham phu khac chi duoc goi SAU chan; neu chan chay dung thi khong cham toi
        ns["_all_level_approvers_already_approved"] = lambda rn, no: False
        try:
            ns["_activate_level"](types.SimpleNamespace(name="REQ-1"), 2)
        except RuntimeError as exc:
            if "DUNG-SAU-CHAN" not in str(exc):
                raise
        return called

    def test_cap_skipped_thi_di_thang_khong_cham_phan_con_lai(self):
        c = self._run_activate(True)
        self.assertEqual(c["advance"], [2])
        self.assertFalse(c["past_guard"], "khong duoc chay tiep vao than ham")

    def test_cap_binh_thuong_thi_chay_tiep_nhu_cu(self):
        c = self._run_activate(False)
        self.assertEqual(c["advance"], [])
        self.assertTrue(c["past_guard"], "cap khong bi bo thi phai kich hoat binh thuong")


class TestDungLuongCoGoi(unittest.TestCase):
    def test_build_snapshot_co_goi_ham_nay(self):
        """Ham dung ma khong ai goi thi vo nghia - va phai goi TRUOC khi cap quyen doc."""
        src = io.open(_TRANS, encoding="utf-8").read()
        tree = ast.parse(src)
        bs = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "build_snapshot"]
        self.assertTrue(bs)
        goi = [n.func.id for n in ast.walk(bs[0])
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertIn("_skip_earlier_duplicate_levels", goi)


if __name__ == "__main__":
    unittest.main(verbosity=2)
