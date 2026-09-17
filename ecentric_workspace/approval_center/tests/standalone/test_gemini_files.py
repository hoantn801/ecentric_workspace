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

    mods = {"frappe": fk, "requests": rq, "ecentric_workspace": pkg,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
