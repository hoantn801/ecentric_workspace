# Copyright (c) 2026, eCentric and contributors
"""p121 xoa DUNG 27 phieu da chot - va xoa bang DUNG co che cho tung loai ban ghi.

Day la patch xoa du lieu PRODUCTION. Khong hoan tac duoc. Nen bo test nay khong hoi "code co
chay khong" ma hoi bon cau co the lam hong that:

  1. PHAM VI. Chi 27 ten da go tay. Neu ai do doi sang bo loc ("phieu tao sau 21/08", "phieu
     cua hoan.tran") thi mot phieu that se bien mat trong lan chay tiep theo. Test giu mot
     phieu moi va mot phieu cu lam moi nhu, va bat neu chung bi dung toi.

  2. CO CHE. `EC Digital Signature Event` va `EC Approval Action` la nhat ky chi-ghi-them:
     mot cai chan o DocPerm, mot cai nem trong `on_trash`. Chung phai di bang `db.delete`.
     Moi thu con lai phai di bang `delete_doc` de con dau vet trong Deleted Document. Doi
     nham chieu nao cung hong: `delete_doc` len nhat ky se 417 giua chung, con `db.delete`
     len phieu se bo qua controller va khong luu dau vet nao.

  3. THU TU. Con truoc cha. Rieng `EC Approval Request.requester_signature_request` phai duoc
     go TRUOC khi xoa chan ky - day dung la cho lan chay bang REST API vap.

  4. CHAY LAI DUOC. Lan chay dau da xoa 166 ban ghi la roi bo cuoc, nen site dang o trang
     thai xoa-do-dang. Patch phai chay tiep tren dong do ma khong no.
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
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_PATCH = os.path.join(_root(), "approval_center", "patches", "p121_purge_esign_test_data.py")

BIZ = "EC Payment Request"
NHAT_KY = ("EC Digital Signature Event", "EC Approval Action")

#: Phieu THAT - khong nam trong danh sach. Neu bat ky phep kiem nao cham vao, test do.
PHIEU_THAT = "EC-PAYR-2026-00001"


class _Store(object):
    """CSDL gia toi thieu: {doctype: {name: {field: value}}}."""

    def __init__(self):
        self.rows = {}
        self.nhat_ky_bi_delete_doc = []   # vi pham co che (se 417/throw tren that)
        self.thuong_bi_db_delete = []     # vi pham co che (mat dau vet)
        self.thu_tu = []                  # nhat ky thao tac, de kiem thu tu
        self.get_all_filters = []

    def them(self, dt, name, **fields):
        self.rows.setdefault(dt, {})[name] = dict(fields)

    def co(self, dt, name):
        return name in self.rows.get(dt, {})


def _khop(row, filters):
    return all(row.get(k) == v for k, v in (filters or {}).items())


def _nap(store):
    """Nap p121 that su, voi mot module `frappe` gia.

    Nap bang `exec(compile(<van ban nguon>))`, KHONG bang `spec_from_file_location`. Loader
    theo duong dan dung lai bytecode trong `__pycache__`, va bo nho dem do chi bi coi la cu
    khi mtime HOAC kich thuoc doi. Mot phep dot bien chuyen mot khoi lenh tu cho nay sang cho
    khac giu nguyen ca hai -> test cham ban .pyc cu, bao XANH, va bao chung cho mot thu tu xoa
    sai. Da xay ra dung nhu vay khi dung bo test nay (01/09).
    """
    f = types.ModuleType("frappe")

    def exists(dt, name=None):
        if isinstance(name, dict):
            return next((n for n, r in store.rows.get(dt, {}).items() if _khop(r, name)), None)
        return name if store.co(dt, name) else None

    def get_all(dt, filters=None, pluck=None, **kw):
        store.get_all_filters.append((dt, dict(filters or {})))
        return [n for n, r in store.rows.get(dt, {}).items() if _khop(r, filters)]

    def count(dt, filters=None):
        return len(get_all(dt, filters))

    def db_delete(dt, filters=None):
        if dt not in NHAT_KY:
            store.thuong_bi_db_delete.append(dt)
        for n in get_all(dt, filters):
            store.thu_tu.append(("db_delete", dt, n))
            store.rows[dt].pop(n, None)

    def delete_doc(dt, name, **kw):
        if dt in NHAT_KY:
            store.nhat_ky_bi_delete_doc.append((dt, name))
        store.thu_tu.append(("delete_doc", dt, name))
        store.rows.get(dt, {}).pop(name, None)

    def get_value(dt, name, field):
        return store.rows.get(dt, {}).get(name, {}).get(field)

    def set_value(dt, name, field, value, **kw):
        store.thu_tu.append(("set_value", dt, name + "." + field))
        store.rows.setdefault(dt, {}).setdefault(name, {})[field] = value

    f.db = types.SimpleNamespace(exists=exists, get_value=get_value, set_value=set_value,
                                 delete=db_delete, count=count)
    f.get_all = get_all
    f.delete_doc = delete_doc
    f.db.exists = exists

    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = f
    try:
        src = io.open(_PATCH, encoding="utf-8").read()
        mod = types.ModuleType("p121_under_test")
        exec(compile(src, _PATCH, "exec"), mod.__dict__)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


def _site_mau():
    """Mot phieu co goi ky day du + mot phieu THAT khong duoc dung toi."""
    s = _Store()
    pr, ar, pkg, dsr = "EC-PAYR-2026-00022", "AR-22", "PKG-22", "DSR-22"

    s.them(BIZ, pr, approval_request=ar)
    s.them("EC Approval Request", ar, requester_signature_request=dsr)
    s.them("EC Digital Signature Package", pkg, business_doctype=BIZ, business_name=pr)
    s.them("EC Digital Signature Request", dsr, package=pkg)
    s.them("EC Digital Signature Placement", "PL-1", package=pkg, signature_file="DSF-1")
    s.them("EC Digital Signature File", "DSF-1", package=pkg)
    s.them("EC Digital Signature Event", "EV-1", package=pkg)
    s.them("EC Digital Signature Event", "EV-2", signature_request=dsr)
    s.them("EC Approval Action", "ACT-1", approval_request=ar)
    s.them("EC Approval Request Level", "LV-1", approval_request=ar)
    s.them("EC Approval Request Approver", "APR-1", approval_request=ar)
    s.them("ToDo", "TD-1", reference_type=BIZ, reference_name=pr)
    s.them("File", "FI-1", attached_to_doctype=BIZ, attached_to_name=pr)

    # Phieu THAT, day du do nghe, khong nam trong danh sach.
    s.them(BIZ, PHIEU_THAT, approval_request="AR-REAL")
    s.them("EC Approval Request", "AR-REAL", requester_signature_request=None)
    s.them("EC Approval Action", "ACT-REAL", approval_request="AR-REAL")
    s.them("File", "FI-REAL", attached_to_doctype=BIZ, attached_to_name=PHIEU_THAT)
    return s


class TestPhamVi(unittest.TestCase):
    def test_phieu_that_khong_bi_dung_toi(self):
        s = _site_mau()
        _nap(s).execute()
        for dt, name in ((BIZ, PHIEU_THAT), ("EC Approval Request", "AR-REAL"),
                         ("EC Approval Action", "ACT-REAL"), ("File", "FI-REAL")):
            self.assertTrue(s.co(dt, name),
                            "%s/%s la du lieu THAT - patch khong duoc cham vao" % (dt, name))

    def test_danh_sach_la_ten_go_tay_khong_phai_bo_loc(self):
        mod = _nap(_Store())
        self.assertEqual(len(mod.PHIEU), 27, "phai dung 27 phieu Hoan da chot")
        self.assertEqual(len(set(mod.PHIEU)), 27, "co ten bi lap")
        for name in mod.PHIEU:
            self.assertRegex(name, r"^EC-PAYR-2026-\d{5}$")
        self.assertNotIn("EC-PAYR-2026-00003", mod.PHIEU,
                         "00003 la nhap cua Administrator tu 10/07 - ngoai dot test")

    def test_khong_he_quet_bang_bo_loc_tren_phieu(self):
        """Neu ai do doi sang get_all(BIZ, {...}) thi pham vi khong con la danh sach nua."""
        s = _site_mau()
        _nap(s).execute()
        quet = [f for dt, f in s.get_all_filters if dt == BIZ]
        self.assertEqual(quet, [],
                         "patch khong duoc TIM phieu de xoa - chi duoc doc theo ten trong "
                         "danh sach. Bo loc la cach nhanh nhat de xoa nham: %s" % quet)


class TestCoChe(unittest.TestCase):
    def test_nhat_ky_di_bang_db_delete(self):
        s = _site_mau()
        _nap(s).execute()
        self.assertEqual(s.nhat_ky_bi_delete_doc, [],
                         "EC Digital Signature Event / EC Approval Action chi-ghi-them: "
                         "delete_doc se 403/throw tren that va patch chet giua chung")
        for dt in NHAT_KY:
            self.assertEqual(s.rows.get(dt, {}), {} if dt == "EC Digital Signature Event"
                             else {"ACT-REAL": s.rows[dt]["ACT-REAL"]},
                             "%s cua phieu test phai bi xoa het" % dt)

    def test_ban_ghi_thuong_di_bang_delete_doc(self):
        s = _site_mau()
        _nap(s).execute()
        self.assertEqual(s.thuong_bi_db_delete, [],
                         "db.delete bo qua controller va khong luu Deleted Document - "
                         "chi danh cho hai bang nhat ky: %s" % s.thuong_bi_db_delete)


class TestThuTu(unittest.TestCase):
    def _vi_tri(self, thu_tu, dt, name=None):
        """Vi tri lenh XOA dau tien tren `dt`.

        Phai loc theo thao tac: `EC Approval Request` con bi `set_value` (go lien ket chan ky)
        TRUOC khi bi xoa, nen neu lay "thao tac dau tien" thi phep do tra ve buoc go lien ket
        va moi so sanh thu tu deu vo nghia.
        """
        for i, (op, d, n) in enumerate(thu_tu):
            if op in ("db_delete", "delete_doc") and d == dt and (name is None or n == name):
                return i
        raise AssertionError("khong thay lenh xoa nao tren %s/%s" % (dt, name))

    def test_con_truoc_cha(self):
        s = _site_mau()
        _nap(s).execute()
        t = s.thu_tu
        cap = [
            ("EC Digital Signature Placement", "EC Digital Signature File"),
            ("EC Digital Signature Event", "EC Digital Signature Request"),
            ("EC Digital Signature File", "EC Digital Signature Package"),
            ("EC Digital Signature Request", "EC Digital Signature Package"),
            ("EC Approval Request Approver", "EC Approval Request"),
            ("EC Approval Request Level", "EC Approval Request"),
            (BIZ, "EC Approval Request"),
        ]
        for con, cha in cap:
            self.assertLess(self._vi_tri(t, con), self._vi_tri(t, cha),
                            "%s phai xoa TRUOC %s, neu khong Frappe chan bang LinkExists"
                            % (con, cha))

    def test_go_lien_ket_chan_ky_truoc_khi_xoa_chan_ky(self):
        s = _site_mau()
        _nap(s).execute()
        t = s.thu_tu
        go = next(i for i, (op, d, n) in enumerate(t)
                  if op == "set_value" and n.endswith(".requester_signature_request"))
        self.assertLess(go, self._vi_tri(t, "EC Digital Signature Request"),
                        "EC Approval Request van tro toi chan ky - phai go lien ket truoc, "
                        "day dung la cho lan chay bang REST API vap")


class TestChayLaiDuoc(unittest.TestCase):
    def test_chay_lan_hai_khong_no_va_khong_xoa_them(self):
        s = _site_mau()
        mod = _nap(s)
        mod.execute()
        con_lai = {dt: set(rows) for dt, rows in s.rows.items() if rows}
        s.thu_tu = []
        mod.execute()   # khong duoc nem
        self.assertEqual(s.thu_tu, [],
                         "lan chay thu hai khong duoc dung vao gi nua: %s" % s.thu_tu)
        self.assertEqual({dt: set(r) for dt, r in s.rows.items() if r}, con_lai)

    def test_chay_tiep_tren_trang_thai_xoa_do_dang(self):
        """Lan chay REST API da xoa 166 ban ghi la roi bo cuoc."""
        s = _site_mau()
        for dt, name in (("EC Approval Request Approver", "APR-1"),
                         ("EC Approval Request Level", "LV-1"),
                         ("EC Digital Signature File", "DSF-1"),
                         ("File", "FI-1")):
            s.rows[dt].pop(name)
        _nap(s).execute()
        self.assertFalse(s.co(BIZ, "EC-PAYR-2026-00022"))
        self.assertFalse(s.co("EC Approval Request", "AR-22"))
        self.assertTrue(s.co(BIZ, PHIEU_THAT))

    def test_phieu_khong_ton_tai_thi_bo_qua(self):
        """Site sach (ban clone, ban moi) - patch phai la khong-lam-gi."""
        s = _Store()
        s.them(BIZ, PHIEU_THAT, approval_request=None)
        _nap(s).execute()
        self.assertEqual(s.thu_tu, [], "site khong co phieu test ma van dung vao gi do")


class TestDaKhaiTrongPatchesTxt(unittest.TestCase):
    def test_co_dong_trong_patches_txt(self):
        import io
        txt = io.open(os.path.join(_root(), "patches.txt"), encoding="utf-8").read()
        self.assertIn("p121_purge_esign_test_data", txt,
                      "patch khong khai trong patches.txt thi khong bao gio chay")


if __name__ == "__main__":
    unittest.main()
