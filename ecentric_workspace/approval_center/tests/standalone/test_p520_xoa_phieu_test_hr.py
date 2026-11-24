# Copyright (c) 2026, eCentric and contributors
"""p520 xoa DUNG cac phieu test 24/11 - pham vi, co che, chay lai duoc.

Nap patch bang exec(compile(src)) (xem ly do trong test_p121_purge_scope: tranh .pyc cu)."""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATCH = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "patches",
                      "p520_xoa_phieu_test_hr_24_11.py")

NHAT_KY = ("EC Approval Action",)
OFFER = "EC-OFFR-2026-00012"


class _Store(object):
    def __init__(self):
        self.rows = {}
        self.nhat_ky_bi_delete_doc = []
        self.thuong_bi_db_delete = []
        self.thu_tu = []
        self.get_all = []

    def them(self, dt, name, **f):
        self.rows.setdefault(dt, {})[name] = dict(f)

    def co(self, dt, name):
        return name in self.rows.get(dt, {})


def _khop(row, flt):
    return all(row.get(k) == v for k, v in (flt or {}).items())


def _nap(s):
    f = types.ModuleType("frappe")

    def exists(dt, name=None):
        return name if s.co(dt, name) else None

    def get_all(dt, filters=None, pluck=None, **kw):
        s.get_all.append((dt, dict(filters or {})))
        return [n for n, r in s.rows.get(dt, {}).items() if _khop(r, filters)]

    def count(dt, filters=None):
        return len([n for n, r in s.rows.get(dt, {}).items() if _khop(r, filters)])

    def db_delete(dt, filters=None):
        if dt not in NHAT_KY:
            s.thuong_bi_db_delete.append(dt)
        for n in [n for n, r in s.rows.get(dt, {}).items() if _khop(r, filters)]:
            s.thu_tu.append(("db_delete", dt, n))
            s.rows[dt].pop(n)

    def delete_doc(dt, name, **kw):
        if dt in NHAT_KY:
            s.nhat_ky_bi_delete_doc.append((dt, name))
        s.thu_tu.append(("delete_doc", dt, name))
        s.rows.get(dt, {}).pop(name, None)

    def get_value(dt, name, field):
        return s.rows.get(dt, {}).get(name, {}).get(field)

    def set_value(dt, name, field, value, **kw):
        s.thu_tu.append(("set_value", dt, name + "." + field))
        s.rows[dt][name][field] = value

    f.db = types.SimpleNamespace(exists=exists, get_value=get_value, set_value=set_value,
                                 delete=db_delete, count=count, table_exists=lambda dt: True)
    f.get_all = get_all
    f.delete_doc = delete_doc
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = f
    try:
        mod = types.ModuleType("p520_under_test")
        exec(compile(io.open(_PATCH, encoding="utf-8").read(), _PATCH, "exec"), mod.__dict__)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


def _site():
    s = _Store()
    s.them("EC Hiring Request", "EC-HIRE-2026-00019", approval_request="EC-APR-2026-01302")
    s.them("EC Offer Request", OFFER, approval_request="EC-APR-2026-01303",
           hiring_request="EC-HIRE-2026-00019", new_staff_preparation="NSP-T")
    s.them("EC New Staff Preparation", "NSP-T", offer_request=OFFER, approval_request="AR-NSP")
    # Adhoc da xoa do dang qua API: chi con phieu + ho so + action + notification.
    s.them("EC Adhoc Approval Request", "EC-ADHOC-2026-00003", approval_request="EC-APR-2026-01304")
    for ar in ("EC-APR-2026-01302", "EC-APR-2026-01303", "EC-APR-2026-01304", "AR-NSP"):
        s.them("EC Approval Request", ar)
        s.them("EC Approval Action", "ACT-" + ar, approval_request=ar)
    s.them("EC Approval Request Level", "LV-1", approval_request="EC-APR-2026-01302")
    s.them("EC Approval Request Approver", "APA-1", approval_request="EC-APR-2026-01303")
    s.them("EC Approval Request Watcher", "W-1", approval_request="AR-NSP")
    s.them("ToDo", "TD-1", reference_type="EC Hiring Request", reference_name="EC-HIRE-2026-00019")
    s.them("Notification Log", "NL-1", document_type="EC Approval Request",
           document_name="EC-APR-2026-01304")
    s.them("Comment", "C-1", reference_doctype="EC Offer Request", reference_name=OFFER)
    # Tep CV test tai len TRUOC khi phieu duoc luu -> khong gan vao phieu nao.
    s.them("File", "a1359e7d95", attached_to_doctype=None, attached_to_name=None)
    # Du lieu THAT
    s.them("EC Offer Request", "EC-OFFR-2026-00011", approval_request="AR-REAL",
           new_staff_preparation="NSP-REAL")
    s.them("EC New Staff Preparation", "NSP-REAL", offer_request="EC-OFFR-2026-00011",
           approval_request="AR-REAL-NSP")
    s.them("EC Approval Request", "AR-REAL")
    s.them("EC Approval Action", "ACT-REAL", approval_request="AR-REAL")
    s.them("EC Approval Request Approver", "APA-REAL", approval_request="AR-REAL")
    s.them("ToDo", "TD-REAL", reference_type="EC Offer Request", reference_name="EC-OFFR-2026-00011")
    s.them("File", "FI-REAL", attached_to_doctype="EC Offer Request",
           attached_to_name="EC-OFFR-2026-00011")
    return s


THAT = (("EC Offer Request", "EC-OFFR-2026-00011"), ("EC New Staff Preparation", "NSP-REAL"),
        ("EC Approval Request", "AR-REAL"), ("EC Approval Action", "ACT-REAL"),
        ("EC Approval Request Approver", "APA-REAL"), ("ToDo", "TD-REAL"), ("File", "FI-REAL"))


class TestPhamVi(unittest.TestCase):
    def test_du_lieu_that_con_nguyen(self):
        s = _site()
        _nap(s).execute()
        for dt, n in THAT:
            self.assertTrue(s.co(dt, n), "%s/%s la du lieu THAT" % (dt, n))

    def test_ten_go_tay(self):
        m = _nap(_Store())
        self.assertEqual([n for _d, n in m.PHIEU_TEST],
                         [OFFER, "EC-HIRE-2026-00019", "EC-ADHOC-2026-00003"])
        self.assertEqual(m.TEP_TEST, ["a1359e7d95"])

    def test_chi_tim_nsp_theo_dung_offer_test(self):
        s = _site()
        _nap(s).execute()
        biz = ("EC Hiring Request", "EC Offer Request", "EC Adhoc Approval Request")
        self.assertEqual([f for dt, f in s.get_all if dt in biz], [], "khong quet phieu bang bo loc")
        self.assertEqual([f for dt, f in s.get_all if dt == "EC New Staff Preparation"],
                         [{"offer_request": OFFER}])


class TestCoChe(unittest.TestCase):
    def test_xoa_het_phieu_test(self):
        s = _site()
        _nap(s).execute()
        for dt, n in (("EC Hiring Request", "EC-HIRE-2026-00019"), ("EC Offer Request", OFFER),
                      ("EC New Staff Preparation", "NSP-T"),
                      ("EC Adhoc Approval Request", "EC-ADHOC-2026-00003"),
                      ("EC Approval Request", "EC-APR-2026-01304"), ("EC Approval Request", "AR-NSP"),
                      ("EC Approval Action", "ACT-EC-APR-2026-01302"), ("Notification Log", "NL-1"),
                      ("File", "a1359e7d95"), ("Comment", "C-1"), ("ToDo", "TD-1"),
                      ("EC Approval Request Watcher", "W-1")):
            self.assertFalse(s.co(dt, n), "%s/%s con sot" % (dt, n))

    def test_nhat_ky_di_db_delete_con_lai_delete_doc(self):
        s = _site()
        _nap(s).execute()
        self.assertEqual(s.nhat_ky_bi_delete_doc, [])
        self.assertEqual(s.thuong_bi_db_delete, [])

    def test_nsp_truoc_offer_truoc_hiring(self):
        s = _site()
        _nap(s).execute()
        xoa = [n for op, dt, n in s.thu_tu if op == "delete_doc"]
        self.assertLess(xoa.index("NSP-T"), xoa.index(OFFER))
        self.assertLess(xoa.index(OFFER), xoa.index("EC-HIRE-2026-00019"))
        self.assertLess(xoa.index("EC-ADHOC-2026-00003"), xoa.index("EC-APR-2026-01304"))

    def test_chay_lai_khong_no(self):
        s = _site()
        m = _nap(s)
        m.execute()
        m.execute()


if __name__ == "__main__":
    unittest.main()
