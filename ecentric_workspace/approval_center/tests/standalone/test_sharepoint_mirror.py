# Copyright (c) 2026, eCentric and contributors
"""Soi guong dinh kem len SharePoint + canh bao "tep doi sau khi duyet" (14/09).

Bo test giu nhung dieu de mat tien neu sai:
  1. DANH SACH CHO PHEP, khong phai danh sach cam - dinh kem phieu nghi viec / phieu luong
     khong duoc tu chay ra mot thu vien ca phong Operation doc duoc.
  2. Mot tep hong khong duoc keo ca phieu khong len duoc tep nao.
  3. Loi SharePoint khong duoc lam hong viec gui phieu (chay nen, nuot loi).
  4. Canh bao chi tinh cap DA DUYET va chi khi moc sua SAU moc duyet - canh bao sai cho thi
     nguoi ta se hoc cach lo no.
  5. Uu tien tep Office: PDF khong sua duoc tren Office Online.
"""
import ast
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


_ROOT = _root()
_MIRROR = os.path.join(_ROOT, "approval_center", "shared", "integrations", "sharepoint_mirror.py")
_QUERY = os.path.join(_ROOT, "approval_center", "shared", "requests", "query_service.py")
_SERVICE = os.path.join(_ROOT, "approval_center", "features", "contract_review",
                        "application", "service.py")


def _doan(path, *ten):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    ra, con_lai = [], set(ten)
    for node in tree.body:
        nn = getattr(node, "name", None)
        if nn is None and isinstance(node, ast.Assign):
            nn = getattr(node.targets[0], "id", None)
        if nn in con_lai:
            ra.append(ast.get_source_segment(src, node))
            con_lai.discard(nn)
    if con_lai:
        raise AssertionError("khong thay %s trong %s" % (", ".join(sorted(con_lai)), path))
    return "\n\n".join(ra)


class _Row(dict):
    """Gia lap `frappe._dict`: doc duoc bang ca khoa lan thuoc tinh."""
    __getattr__ = dict.get


class _FrappeGia(object):
    def __init__(self, tep=None, lien_ket=None):
        self._tep = tep or []
        self._lien = lien_ket or []
        self.log = []
        self.enqueued = []

    def get_all(self, dt, **kw):
        if dt == "File":
            return [_Row(t) for t in self._tep]
        if dt == "EC SharePoint File Link":
            urls = dict(kw.get("filters") or {}).get("file_url")
            keep = urls[1] if isinstance(urls, (list, tuple)) and len(urls) == 2 else None
            return [_Row(r) for r in self._lien if keep is None or r["file_url"] in keep]
        return []

    def log_error(self, *a, **k):
        self.log.append(a)

    def get_traceback(self):
        return "tb"

    def enqueue(self, method, **kw):
        self.enqueued.append((method, kw))


def _nap_mirror(frappe_gia, tai_len=None, ghi=None):
    ns = {"frappe": frappe_gia}
    ns["wr_sp"] = types.SimpleNamespace(get_app_token=lambda: "TOKEN")

    class SharePointChuaSan(Exception):
        pass

    ns["SharePointChuaSan"] = SharePointChuaSan
    ns["tai_len"] = tai_len or (lambda *a, **k: {"item_id": "I", "web_url": "U"})
    ns["ghi_lien_ket"] = ghi or (lambda *a, **k: None)
    exec(compile(_doan(_MIRROR, "THU_MUC_THEO_PHIEU", "duoc_soi_guong", "_dinh_kem",
                       "dong_bo_phieu", "dong_bo_nen"), "<m>", "exec"), ns)
    return ns


TEP = [{"file_name": "hd.pdf", "file_url": "/f/hd.pdf"},
       {"file_name": "hd.docx", "file_url": "/f/hd.docx"}]
DT = "EC Contract Review Request"


class DanhSachChoPhep(unittest.TestCase):
    def test_chi_loai_phieu_duoc_khai_moi_duoc_soi_guong(self):
        ns = _nap_mirror(_FrappeGia(TEP))
        self.assertTrue(ns["duoc_soi_guong"](DT))
        for khac in ("EC Resignation Request", "EC Payment Request", "EC Booking Request"):
            self.assertFalse(ns["duoc_soi_guong"](khac), khac + " KHONG duoc tu dong len SharePoint")

    def test_phieu_ngoai_danh_sach_thi_khong_goi_graph(self):
        goi = []
        ns = _nap_mirror(_FrappeGia(TEP), tai_len=lambda *a, **k: goi.append(a))
        kq = ns["dong_bo_phieu"]("EC Resignation Request", "EC-RESN-1")
        self.assertEqual(goi, [])
        self.assertEqual(kq["so_tep"], 0)
        self.assertIn("bo_qua", kq)


class MotTepHongKhongKeoCaPhieu(unittest.TestCase):
    def test_tep_loi_duoc_ghi_log_va_cac_tep_khac_van_len(self):
        def tai(bdt, url, ten, name, token=None):
            if ten == "hd.pdf":
                raise RuntimeError("Graph 500")
            return {"item_id": "I", "web_url": "U"}
        f = _FrappeGia(TEP)
        kq = _nap_mirror(f, tai_len=tai)["dong_bo_phieu"](DT, "EC-CTR-1")
        self.assertEqual(kq["xong"], ["hd.docx"])
        self.assertEqual(kq["hong"], ["hd.pdf"])
        self.assertTrue(f.log, "tep hong phai duoc ghi log de con sua")


class ChayNenNuotLoi(unittest.TestCase):
    def test_dong_bo_nen_khong_bao_gio_nem_ra(self):
        def no(*a, **k):
            raise RuntimeError("mat mang")
        f = _FrappeGia(TEP)
        ns = _nap_mirror(f)
        ns["dong_bo_phieu"] = no
        self.assertIsNone(ns["dong_bo_nen"](DT, "EC-CTR-1"))
        self.assertTrue(f.log)

    def test_gui_phieu_dat_soi_guong_vao_HANG_DOI_chu_khong_goi_thang(self):
        src = io.open(_SERVICE, encoding="utf-8").read()
        self.assertIn("frappe.enqueue", src,
                      "tai vai MB len Graph ma goi thang thi man hinh gui phieu treo")
        self.assertIn("sharepoint_mirror.dong_bo_nen", src)

    def test_loi_enqueue_khong_lam_hong_viec_gui(self):
        src = _doan(_SERVICE, "_soi_guong_sharepoint")
        self.assertIn("try:", src)
        self.assertIn("except Exception:", src)
        self.assertNotIn("raise", src, "su co cua Microsoft khong duoc lam hong mot lan gui phieu")

    def test_gui_lai_cung_soi_guong_lai(self):
        """Gui lai thuong di kem THAY tep - khong soi guong lai thi nguoi duyet mo ban cu."""
        src = io.open(_SERVICE, encoding="utf-8").read()
        i = src.index("def resubmit(")
        j = src.index("def _guard_resubmit_needs_ceo(")
        self.assertIn("_soi_guong_sharepoint", src[i:j])


class UuTienTepOffice(unittest.TestCase):
    def test_docx_dung_truoc_pdf(self):
        ns = _nap_mirror(_FrappeGia(TEP))
        ten = [t["file_name"] for t in ns["_dinh_kem"](DT, "EC-CTR-1")]
        self.assertEqual(ten[0], "hd.docx", "PDF khong sua duoc tren Office Online")

    def test_khong_mat_tep_nao(self):
        ns = _nap_mirror(_FrappeGia(TEP))
        self.assertEqual(len(ns["_dinh_kem"](DT, "EC-CTR-1")), len(TEP))


def _nap_gan(frappe_gia):
    import datetime as _dt

    ns = {"frappe": frappe_gia}

    def _get_datetime(v):
        if isinstance(v, _dt.datetime):
            return v
        return _dt.datetime.strptime(str(v), "%Y-%m-%d %H:%M:%S")

    ns["get_datetime"] = _get_datetime
    exec(compile(_doan(_QUERY, "gan_sharepoint"), "<q>", "exec"), ns)
    return ns["gan_sharepoint"]


LIEN = [{"file_url": "/f/hd.docx", "sp_web_url": "https://sp/hd.docx",
         "sp_last_modified": "2026-09-14 18:00:00"}]


class CanhBaoSuaSauDuyet(unittest.TestCase):
    def setUp(self):
        self.gan = _nap_gan(_FrappeGia(lien_ket=LIEN))

    def _dk(self):
        return [{"file_name": "hd.docx", "file_url": "/f/hd.docx"}]

    def test_gan_link_sharepoint(self):
        ra = self.gan(self._dk(), [])
        self.assertEqual(ra[0]["sp_web_url"], "https://sp/hd.docx")

    def test_bao_dung_cap_duyet_TRUOC_luc_sua(self):
        approvers = [{"approver": "a@x.vn", "level_no": 1, "status": "Approved",
                      "decided_at": "2026-09-14 17:00:00"},
                     {"approver": "b@x.vn", "level_no": 2, "status": "Approved",
                      "decided_at": "2026-09-14 19:00:00"}]
        ds = self.gan(self._dk(), approvers)[0]["sp_sua_sau_duyet"]
        self.assertEqual([x["approver"] for x in ds], ["a@x.vn"],
                         "chi cap duyet TRUOC 18:00 moi la nguoi duyet ban cu")

    def test_khong_tinh_cap_chua_duyet(self):
        approvers = [{"approver": "c@x.vn", "level_no": 1, "status": "Pending",
                      "decided_at": "2026-09-14 17:00:00"},
                     {"approver": "d@x.vn", "level_no": 2, "status": "Rejected",
                      "decided_at": "2026-09-14 17:00:00"},
                     {"approver": "e@x.vn", "level_no": 3, "status": "Skipped",
                      "decided_at": "2026-09-14 17:00:00"}]
        self.assertEqual(self.gan(self._dk(), approvers)[0]["sp_sua_sau_duyet"], [])

    def test_chua_ai_duyet_thi_khong_canh_bao(self):
        self.assertEqual(self.gan(self._dk(), [])[0]["sp_sua_sau_duyet"], [])

    def test_tep_khong_co_ban_sharepoint_thi_khong_dung_gi(self):
        dk = [{"file_name": "khac.pdf", "file_url": "/f/khac.pdf"}]
        ra = self.gan(dk, [{"approver": "a@x.vn", "level_no": 1, "status": "Approved",
                            "decided_at": "2026-09-14 17:00:00"}])
        self.assertNotIn("sp_web_url", ra[0])
        self.assertNotIn("sp_sua_sau_duyet", ra[0])

    def test_khong_co_dinh_kem_thi_khong_truy_van(self):
        f = _FrappeGia(lien_ket=LIEN)
        self.assertEqual(_nap_gan(f)([], []), [])


class MuiGioTaiCHO_GOI(unittest.TestCase):
    """`gio_he_thong` dung khong chua du - phai chac CHO GOI co dung no.

    14/09 chuyen module tu `features/.../sharepoint_sync.py` sang `shared/integrations/` thi
    ham doi mui gio bi rot mat trong luc merge. Bo test cu chi kiem chinh cai ham nen van xanh:
    ham dung, ma khong ai goi. Hai bai duoi day kiem DIEM GOI.
    """

    def _nap(self, requests_gia=None, doc=None):
        import datetime as _dt

        ns = {"TIMEOUT": 30, "LINK_DT": "EC SharePoint File Link",
              "_requests": lambda: requests_gia,
              "_graph": lambda: "https://g",
              "now_datetime": lambda: _dt.datetime(2026, 9, 14, 18, 0, 0),
              "wr_sp": types.SimpleNamespace(SITE_ID="s", get_app_token=lambda: "T")}

        class _Db(object):
            def get_value(self, *a, **k):
                return None

        ns["frappe"] = types.SimpleNamespace(
            db=_Db(), get_doc=lambda *a: doc, new_doc=lambda *a: doc)

        def _get_datetime(txt):
            return _dt.datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")

        mod = types.ModuleType("frappe.utils")
        mod.get_datetime = _get_datetime
        mod.convert_utc_to_system_timezone = lambda d: (d + _dt.timedelta(hours=7)).replace(
            tzinfo=_dt.timezone(_dt.timedelta(hours=7)))
        fr = types.ModuleType("frappe")
        fr.utils = mod
        self._cu = (sys.modules.get("frappe"), sys.modules.get("frappe.utils"))
        sys.modules["frappe"] = fr
        sys.modules["frappe.utils"] = mod
        exec(compile(_doan(_MIRROR, "gio_he_thong", "ghi_lien_ket", "doc_moc_sua"), "<m>", "exec"), ns)
        return ns

    def tearDown(self):
        for ten, cu in zip(("frappe", "frappe.utils"), getattr(self, "_cu", (None, None))):
            if cu is None:
                sys.modules.pop(ten, None)
            else:
                sys.modules[ten] = cu

    def test_module_THAT_co_import_now_datetime(self):
        """Ban gia trong `_nap` TU TIEM `now_datetime` vao khong gian ten - nen bo test nay
        van xanh trong khi module that THIEU dong import, va production nem NameError o viec
        chay nen (EC-CTR-2026-00014, 15/09). Mot phep kiem tu cap cho minh thu ma ban that
        khong co thi no chi dang do chinh cai gia no dung len.

        Cong tong quat cho ca lop loi nay la `tests/test_no_undefined_names.py` (pyflakes);
        phep kiem o day la chot thu hai, ngay canh cho da dau."""
        src = io.open(_MIRROR, encoding="utf-8").read()
        self.assertIn("from frappe.utils import now_datetime", src)

    def test_ghi_lien_ket_luu_GIO_HE_THONG_chu_khong_phai_chuoi_UTC(self):
        class _Doc(object):
            def save(self, **k):
                pass
            name = "X"

        doc = _Doc()
        ns = self._nap(doc=doc)
        ns["ghi_lien_ket"]("DT", "/f/a.docx", "EC-CTR-1",
                           {"item_id": "I", "web_url": "U",
                            "last_modified": "2026-09-14T08:58:18Z"})
        self.assertEqual(doc.sp_last_modified.hour, 15,
                         "08:58 UTC phai thanh 15:58 - luu chuoi UTC tho thi MariaDB nem 1292, "
                         "va moi phep so voi moc duyet lech 7 tieng")
        self.assertIsNone(getattr(doc.sp_last_modified, "tzinfo", None))

    def test_doc_moc_sua_tra_datetime_da_doi_chu_khong_phai_chuoi_ISO(self):
        resp = _Resp(200, {"lastModifiedDateTime": "2026-09-14T08:58:18Z"})
        ns = self._nap(requests_gia=types.SimpleNamespace(
            get=lambda *a, **k: resp))
        ra = ns["doc_moc_sua"]("ITEM")
        self.assertFalse(isinstance(ra, str),
                         "tra chuoi ISO thi moi cho goi phai tu nho doi mui gio - cho nao quen "
                         "thi lech 7 tieng mot cach im lang")
        self.assertEqual(ra.hour, 15)


class _Resp(object):
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


if __name__ == "__main__":
    unittest.main(verbosity=1)
