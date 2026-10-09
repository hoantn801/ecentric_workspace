# Copyright (c) 2026, eCentric and contributors
"""Cap quyen SharePoint phai thay DU nguoi trong luong (09/10/2026, EC-CTR-2026-00036).

Job soi guong chay truoc khi giao dich gui phieu commit -> `approval_request` tren phieu con
trong -> chi cap cho nguoi gui; 8 nguoi duyet bam "Mo online" an "You need access"."""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_MIRROR = os.path.join(_ROOT, "approval_center", "shared", "integrations", "sharepoint_mirror.py")
_SERVICE = os.path.join(_ROOT, "approval_center", "features", "contract_review",
                        "application", "service.py")
_PATCH = os.path.join(_ROOT, "approval_center", "patches", "p285_cap_bu_quyen_sharepoint_thieu_nguoi.py")


def _doan(path, *ten):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = [ast.get_source_segment(src, n) for n in tree.body if getattr(n, "name", None) in ten]
    assert len(out) == len(ten), ten
    return "\n\n".join(out)


class _Row(dict):
    __getattr__ = dict.get


def _frappe(phieu, ar_theo_tham_chieu, nguoi_duyet):
    f = types.SimpleNamespace()
    f.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda fn: False)
    f.db = types.SimpleNamespace(get_value=lambda dt, n, fields, as_dict=False: _Row(phieu))

    def get_all(dt, filters=None, **kw):
        if dt == "EC Approval Request":
            assert filters == {"reference_doctype": "EC Contract Review Request",
                               "reference_name": "EC-CTR-2026-00036"}
            return list(ar_theo_tham_chieu)
        if dt == "EC Approval Request Approver":
            return list(nguoi_duyet.get(filters["approval_request"], []))
        return []
    f.get_all = get_all
    return f


def _nap(f):
    ns = {"frappe": f}
    exec(compile(_doan(_MIRROR, "nguoi_trong_luong", "_phieu_duyet_theo_tham_chieu"), "<m>", "exec"), ns)
    return ns["nguoi_trong_luong"]


DUYET = {"EC-APR-2026-00672": ["tuan.ly@e.vn", "thu.trinh@e.vn", "phuong.nguyen1@e.vn"]}


class NguoiTrongLuong(unittest.TestCase):
    def test_truong_approval_request_trong_van_tim_ra_nguoi_duyet(self):
        f = _frappe({"requested_by": "huong.pham@e.vn", "approval_request": None},
                    ["EC-APR-2026-00672"], DUYET)
        self.assertEqual(_nap(f)("EC Contract Review Request", "EC-CTR-2026-00036"),
                         ["huong.pham@e.vn", "tuan.ly@e.vn", "thu.trinh@e.vn", "phuong.nguyen1@e.vn"])

    def test_co_truong_thi_dung_truong(self):
        f = _frappe({"requested_by": "huong.pham@e.vn", "approval_request": "EC-APR-2026-00672"},
                    [], DUYET)
        self.assertEqual(len(_nap(f)("EC Contract Review Request", "EC-CTR-2026-00036")), 4)

    def test_chua_co_phieu_duyet_nao_chi_con_nguoi_gui(self):
        f = _frappe({"requested_by": "huong.pham@e.vn"}, [], DUYET)
        self.assertEqual(_nap(f)("EC Contract Review Request", "EC-CTR-2026-00036"),
                         ["huong.pham@e.vn"])


class JobDoiCommit(unittest.TestCase):
    def test_soi_guong_dat_viec_SAU_commit(self):
        src = _doan(_SERVICE, "_soi_guong_sharepoint")
        self.assertIn("enqueue_after_commit=True", src)


class PatchCapBu(unittest.TestCase):
    def _chay(self, rows):
        enq, logs = [], []
        f = types.SimpleNamespace(
            db=types.SimpleNamespace(exists=lambda *a: True),
            get_all=lambda dt, **kw: [_Row(r) for r in rows],
            enqueue=lambda m, **kw: enq.append((m, kw)),
            log_error=lambda *a, **k: logs.append(a),
            get_traceback=lambda: "tb")
        ns = {"frappe": f}
        src = io.open(_PATCH, encoding="utf-8").read().replace("import frappe\n", "")
        exec(compile(src, "<p>", "exec"), ns)
        ns["execute"]()
        return enq

    def test_chi_dat_viec_cho_tep_mot_nguoi_va_khong_tai_lai(self):
        enq = self._chay([
            {"name": "L1", "sp_granted_to": "huong.pham@e.vn"},
            {"name": "L2", "sp_granted_to": "a@e.vn, b@e.vn"},
            {"name": "L3", "sp_granted_to": ""}])
        self.assertEqual([kw["ten_ban_ghi"] for _, kw in enq], ["L1", "L3"])
        self.assertTrue(all(m.endswith("sharepoint_mirror.cap_bu_link") for m, _ in enq))
        self.assertTrue(all(kw.get("enqueue_after_commit") for _, kw in enq))

    def test_khong_nem_loi(self):
        f = types.SimpleNamespace(db=types.SimpleNamespace(exists=lambda *a: 1 / 0),
                                  log_error=lambda *a, **k: None, get_traceback=lambda: "tb")
        ns = {"frappe": f}
        src = io.open(_PATCH, encoding="utf-8").read().replace("import frappe\n", "")
        exec(compile(src, "<p>", "exec"), ns)
        ns["execute"]()


if __name__ == "__main__":
    unittest.main()
