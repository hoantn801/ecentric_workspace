# Copyright (c) 2026, eCentric and contributors
"""Tang Gemini cua G2: `upload_bytes` tach ra va `generate_json(files=)`.

HAI THU KHONG DUOC SAI AM THAM:

  1. `upload_bytes` duoc TACH RA tu than `upload_from_sp_url`, va duong SharePoint van phai
     goi vao no. Neu refactor lam hai duong tach doi thi mot cai sua o buoc tai len chi chay
     cho mot ben - va khong co exception nao bao dieu do.
  2. `generate_json` phai gui phan `fileData` dung hinh dang. Gui sai khoa thi Gemini bo qua
     tep VA VAN TRA VE JSON hop le tu mot minh doan van ban: form duoc dien, chi la tep chua
     bao gio duoc doc. Do la loi te nhat cua ca G2 nen no phai co test rieng.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "gemini_api.py"))

KHOA = "AIza-KHOA-BI-MAT-KHONG-DUOC-LOT-RA"


class _Resp(object):
    def __init__(self, payload=None, boom=None):
        self._payload, self._boom = payload, boom
    def raise_for_status(self):
        if self._boom:
            raise RuntimeError(self._boom)
    def json(self):
        return self._payload


def _load(settings=None, post=None):
    """post(url, **kw) -> _Resp. Tra (module, calls)."""
    calls = []
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    _s = dict(settings or {})

    class _DB:
        def get_single_value(self, dt, field):
            return _s.get(field)
    fk.db = _DB()
    fk.conf = {}
    fk.whitelist = lambda *a, **k: (lambda f: f)

    # frappe.utils.password.get_decrypted_password - duong DUY NHAT doc duoc truong Password
    up = types.ModuleType("frappe.utils")
    upw = types.ModuleType("frappe.utils.password")
    def _decrypt(dt, dn, fieldname, raise_exception=True):
        return _s.get("__auth__" + fieldname)
    upw.get_decrypted_password = _decrypt
    up.password = upw

    rq = types.ModuleType("requests")
    def _post(url, **kw):
        calls.append(dict(kw, url=url))
        return post(url, **kw) if post else _Resp({})
    def _get(url, **kw):
        calls.append(dict(kw, url=url, method="GET"))
        return _Resp({"state": "ACTIVE"})
    rq.post, rq.get = _post, _get

    # `_extract_rel_path` uy quyen sang weekly_report.sharepoint (mot cho biet hinh dang URL
    # cua SharePoint). Test nay khong kiem cai do nen gia lap tra ve duong dan co san.
    pkg = types.ModuleType("ecentric_workspace"); pkg.__path__ = []
    wr = types.ModuleType("ecentric_workspace.weekly_report"); wr.__path__ = []
    sp = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
    sp.rel_path_from_web_url = lambda url, dept: "Weekly Reports/Service/bc.pdf"
    wr.sharepoint = sp; pkg.weekly_report = wr

    mods = {"frappe": fk, "requests": rq,
            "frappe.utils": up, "frappe.utils.password": upw,
            "ecentric_workspace": pkg,
            "ecentric_workspace.weekly_report": wr,
            "ecentric_workspace.weekly_report.sharepoint": sp}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_gemini_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "gemini_api.py", "exec"), m.__dict__)
        m._calls, m._mods = calls, mods
        return m, calls
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _run(m, fn):
    """Chay `fn` VOI cac module gia duoc cam vao sys.modules.

    Can cho bat ky duong nao import LUC CHAY (`api_key()` lam `from frappe.utils.password
    import ...`). Module globals giu duoc `frappe` gia tu luc exec, nhung mot import luc
    chay thi di thang vao sys.modules - noi ma cac ban gia da bi go ra."""
    saved = {k: sys.modules.get(k) for k in m._mods}
    sys.modules.update(m._mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


OK_UPLOAD = _Resp({"file": {"uri": "files/abc", "expirationTime": "2026-09-18T00:00:00Z"}})


class TestUploadBytes(unittest.TestCase):
    def test_mime_di_vao_content_type(self):
        # Gemini doc kieu tep tu header nay. Gui "application/pdf" cho mot tep PNG thi no
        # nhan roi doc ra rac - khong loi, chi sai.
        m, calls = _load(post=lambda url, **kw: OK_UPLOAD)
        out = m.upload_bytes(b"xxx", "anh.png", "image/png", KHOA, wait_active=False)
        self.assertTrue(out["success"])
        self.assertEqual(out["mime_type"], "image/png")
        self.assertEqual(calls[0]["headers"]["Content-Type"], "image/png")
        self.assertEqual(calls[0]["headers"]["x-goog-api-key"], KHOA)

    def test_ten_tep_len_header_duoc_ascii_hoa(self):
        m, calls = _load(post=lambda url, **kw: OK_UPLOAD)
        m.upload_bytes(b"x", u"hoá đơn tháng 8.pdf", "application/pdf", KHOA, wait_active=False)
        header = calls[0]["headers"]["X-Goog-Upload-File-Name"]
        self.assertEqual(header, header.encode("ascii", "ignore").decode("ascii"))

    def test_khoa_bi_xoa_khoi_thong_diep_loi(self):
        def boom(url, **kw):
            raise RuntimeError("401 tren ...?key=" + KHOA)
        m, _ = _load(post=boom)
        out = m.upload_bytes(b"x", "a.pdf", "application/pdf", KHOA, wait_active=False)
        self.assertFalse(out["success"])
        self.assertNotIn(KHOA, out["error"])

    def test_2xx_nhung_khong_co_uri_van_la_hong(self):
        m, _ = _load(post=lambda url, **kw: _Resp({"file": {}}))
        out = m.upload_bytes(b"x", "a.pdf", "application/pdf", KHOA, wait_active=False)
        self.assertFalse(out["success"])

    def test_upload_file_bytes_doc_khoa_server_side(self):
        m, calls = _load(settings={"ec_gemini_api_key": KHOA},
                         post=lambda url, **kw: OK_UPLOAD)
        out = m.upload_file_bytes(b"x", "a.pdf", "application/pdf", wait_active=False)
        self.assertTrue(out["success"])
        self.assertEqual(calls[0]["headers"]["x-goog-api-key"], KHOA)

    def test_khong_co_khoa_thi_bao_no_key_chu_khong_goi(self):
        m, calls = _load(settings={}, post=lambda url, **kw: OK_UPLOAD)
        out = m.upload_file_bytes(b"x", "a.pdf", "application/pdf")
        self.assertEqual(out["error"], "no_key")
        self.assertEqual(calls, [])


class TestSharePointVanGoiVaoUploadBytes(unittest.TestCase):
    """Duong SharePoint phai di QUA `upload_bytes`, khong duoc co ban sao thu hai."""

    def _sp(self, m, goi):
        m.upload_bytes = goi
        saved = {k: sys.modules.get(k) for k in m._mods}
        sys.modules.update(m._mods)
        try:
            # Graph tra ve bytes PDF hop le.
            return m.upload_from_sp_url(
                "https://boxmeglobal.sharepoint.com/sites/x/Shared%20Documents/Service/bc.pdf",
                "GRAPH-TOKEN", KHOA, dept_clean="Service", wait_active=False)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_duong_sharepoint_goi_upload_bytes(self):
        m, _ = _load()
        class _R(object):
            content = b"%PDF-1.7 " + b"x" * 200
            def raise_for_status(self): pass
        m.requests.get = lambda url, **kw: _R()
        thay = {}
        def goi(data, filename, mime, key, wait_active=True, timeout=None):
            thay.update({"filename": filename, "mime": mime, "bytes": len(data)})
            return {"success": True, "uri": "files/sp", "mime_type": mime,
                    "name": filename, "display_name": filename, "expires_at": "",
                    "active": None}
        out = self._sp(m, goi)
        self.assertTrue(out["success"], out.get("error"))
        self.assertEqual(thay["mime"], "application/pdf")
        self.assertEqual(out["uri"], "files/sp")
        # size_bytes van la kich thuoc PDF tai ve, khong bi ghi de boi `upload_bytes`.
        self.assertEqual(out["size_bytes"], thay["bytes"])

    def test_upload_hong_thi_sharepoint_tra_error_chu_khong_success(self):
        m, _ = _load()
        class _R(object):
            content = b"%PDF-1.7 " + b"x" * 200
            def raise_for_status(self): pass
        m.requests.get = lambda url, **kw: _R()
        def goi(data, filename, mime, key, wait_active=True, timeout=None):
            return {"success": False, "error": "hong", "name": filename,
                    "display_name": filename}
        out = self._sp(m, goi)
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "hong")
        # Ten van co du upload hong - nguoi goi dung de bao "tep X khong len duoc".
        self.assertTrue(out["name"])


class TestGenerateJsonFiles(unittest.TestCase):
    OK = _Resp({"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]})

    def _goi(self, files):
        m, calls = _load(settings={"ec_gemini_api_key": KHOA},
                         post=lambda url, **kw: self.OK)
        out = m.generate_json("PROMPT", {"type": "object"}, files=files)
        return out, calls[0]["json"]["contents"][0]["parts"]

    def test_fileData_dung_hinh_dang_va_dung_TRUOC_van_ban(self):
        out, parts = self._goi([{"uri": "files/abc", "mime_type": "application/pdf"}])
        self.assertTrue(out["ok"])
        self.assertEqual(parts[0], {"fileData": {"fileUri": "files/abc",
                                                 "mimeType": "application/pdf"}})
        self.assertEqual(parts[-1], {"text": "PROMPT"})

    def test_nhieu_tep_giu_dung_thu_tu(self):
        _, parts = self._goi([{"uri": "f/1", "mime_type": "image/png"},
                              {"uri": "f/2", "mime_type": "application/pdf"}])
        self.assertEqual([p["fileData"]["fileUri"] for p in parts[:2]], ["f/1", "f/2"])
        self.assertEqual(len(parts), 3)

    def test_khong_co_tep_thi_than_request_giong_het_G1(self):
        out, parts = self._goi(None)
        self.assertEqual(parts, [{"text": "PROMPT"}])

    def test_muc_thieu_uri_bi_bo_chu_khong_gui_khoa_rong(self):
        # Gui {"fileUri": ""} len thi Gemini tra 400 cho CA luot - mot muc rac lam hong
        # ca nhung tep tot di cung.
        _, parts = self._goi([{"mime_type": "application/pdf"}, {"uri": "f/3"}])
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["fileData"]["fileUri"], "f/3")


class TestLoiPhaiTuNoiDuocNguyenNhan(unittest.TestCase):
    """17/09: mot loi 400 that lam ca tinh nang chet, dong log chi noi duoc "400 Bad Request".

    `HTTPError` chi mang ma so va URL; ly do nam trong THAN phan hoi. Vut than di la bien
    mot su co 5 phut thanh mot cuoc do dam."""

    def _boom(self, payload=None, text=""):
        class _R(object):
            def raise_for_status(self_):
                raise RuntimeError("400 Client Error: Bad Request for url: https://x")
            def json(self_):
                if payload is None:
                    raise ValueError("khong phai json")
                return payload
        r = _R()
        r.text = text
        return r

    def test_ly_do_cua_gemini_di_vao_error(self):
        r = self._boom({"error": {"message": "Invalid JSON payload received.",
                                  "status": "INVALID_ARGUMENT"}})
        m, _ = _load(settings={"ec_gemini_api_key": KHOA}, post=lambda url, **kw: r)
        out = m.generate_json("P", {"type": "object"})
        self.assertFalse(out["ok"])
        self.assertIn("Invalid JSON payload received.", out["error"])
        self.assertIn("INVALID_ARGUMENT", out["error"])

    def test_than_khong_phai_json_thi_lay_text(self):
        r = self._boom(payload=None, text="<html>502 upstream</html>")
        m, _ = _load(settings={"ec_gemini_api_key": KHOA}, post=lambda url, **kw: r)
        out = m.generate_json("P", {"type": "object"})
        self.assertIn("502 upstream", out["error"])

    def test_khoa_van_bi_xoa_khoi_than(self):
        r = self._boom({"error": {"message": "key " + KHOA + " invalid"}})
        m, _ = _load(settings={"ec_gemini_api_key": KHOA}, post=lambda url, **kw: r)
        out = m.generate_json("P", {"type": "object"})
        self.assertNotIn(KHOA, out["error"])

    def test_khong_co_phan_hoi_thi_khong_no(self):
        def boom(url, **kw):
            raise RuntimeError("connection reset")
        m, _ = _load(settings={"ec_gemini_api_key": KHOA}, post=boom)
        out = m.generate_json("P", {"type": "object"})
        self.assertIn("connection reset", out["error"])


class TestKhoaDocTuDuongPassword(unittest.TestCase):
    """SU CO 17/09 - ca duong AI dien ho chet tu G1 vi MOT dong doc khoa sai duong.

    `ec_gemini_api_key` la truong kieu **Password**. Frappe cat bi mat sang bang `__Auth` va
    de lai trong cot cua tai lieu dung mot chuoi dau sao CUNG DO DAI. Doc bang
    `frappe.db.get_single_value` thi ra 39 dau sao - dung kieu, dung do dai, sai hoan toan.
    Google tra "API key not valid", dong log cua ta chi thay "400 Bad Request".

    Day la loai loi khong cach nao bat duoc bang doc code: no chi lo ra khi goi that. Nen
    phep kiem o day khong hoi "co goi get_decrypted_password khong" ma hoi "khoa NAO di ra
    tren day".
    """

    OK = _Resp({"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]})

    def test_khoa_that_di_ra_tren_day_chu_khong_phai_mat_na(self):
        m, calls = _load(settings={"ec_gemini_api_key": "*" * 39,
                                   "__auth__ec_gemini_api_key": KHOA},
                         post=lambda url, **kw: self.OK)
        out = _run(m, lambda: m.generate_json("P", {"type": "object"}))
        self.assertTrue(out["ok"])
        self.assertEqual(calls[0]["headers"]["x-goog-api-key"], KHOA)

    def test_chi_doc_ra_mat_na_thi_coi_nhu_KHONG_CO_khoa(self):
        # Gui mat na di = doi lay mot loi 400 vo nghia. Noi thang "khong co khoa" thi sua
        # duoc trong 5 phut.
        m, calls = _load(settings={"ec_gemini_api_key": "*" * 39},
                         post=lambda url, **kw: self.OK)
        out = _run(m, lambda: m.generate_json("P", {"type": "object"}))
        self.assertEqual(out["error"], "no_key")
        self.assertEqual(calls, [])          # va KHONG duoc goi di

    def test_upload_cung_di_qua_duong_do(self):
        m, calls = _load(settings={"ec_gemini_api_key": "*" * 39,
                                   "__auth__ec_gemini_api_key": KHOA},
                         post=lambda url, **kw: OK_UPLOAD)
        out = _run(m, lambda: m.upload_file_bytes(b"x", "a.pdf", "application/pdf",
                                                  wait_active=False))
        self.assertTrue(out["success"])
        self.assertEqual(calls[0]["headers"]["x-goog-api-key"], KHOA)

    def test_upload_tu_choi_mat_na(self):
        m, calls = _load(settings={"ec_gemini_api_key": "*" * 39},
                         post=lambda url, **kw: OK_UPLOAD)
        out = _run(m, lambda: m.upload_file_bytes(b"x", "a.pdf", "application/pdf"))
        self.assertEqual(out["error"], "no_key")
        self.assertEqual(calls, [])

    def test_looks_masked(self):
        m, _ = _load()
        self.assertTrue(m._looks_masked("*" * 39))
        self.assertFalse(m._looks_masked("AIzaSyABC"))
        self.assertFalse(m._looks_masked(""))
        self.assertFalse(m._looks_masked("AIza***"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
