# Copyright (c) 2026, eCentric and contributors
"""PR-J (24/11/2026): xuat PDF tu .docx phia server + go ket chan duyet + tu huy tai lieu hop dong.

  A. platform/docconvert.docx_to_pdf (Microsoft Graph, transport gia):
     - chua cau hinh thu vien tam -> tu choi, KHONG goi mang (quyen rieng tu PII - PO 17/11);
     - tep nho: PUT /content -> GET ?format=pdf (theo 302) -> permanentDelete; ten tep tam ngau
       nhien (khong lo ten hop dong); ket qua phai bat dau %PDF;
     - tep lon: createUploadSession + khuc Content-Range, KHONG gui Authorization toi uploadUrl;
     - hong o bat ky buoc nao -> van XOA tep tam (co ma -> theo ma; chua co ma -> theo duong
       dan; khuc tai hong -> huy phien uploadUrl); xoa vinh vien hong -> DELETE + ToDo ops;
     - han tong DEADLINE; sweep_temp xoa tep tam cu (so gio UTC);
     - thong bao loi khong chua token / noi dung tep.
     api.convert_business_docx_to_pdf (chay that voi frappe gia): POST, chi nguoi tao, duong dan
     /files|/private/files, tep dinh kem DUNG phieu, chi .docx, <=10MB (kiem file_size truoc khi
     doc), phieu da ket thuc -> tu choi, khoa mot lan chuyen / phieu, PDF rieng tu cung phieu.
  B. authorize_resend cho chan Approve (buoc khong ky / nguoi lap): chi khi canh cua buoc DANG MO
     tren cong ngay luc do; cong da roi buoc / khong doc duoc / ke hoach khong phai transition
     -> tu choi, KHONG dat co; lan thu cuoi < 10 phut -> tu choi. Chan ky (Sign) giu luat cu.
  C. provider_cancel: hop dong vao AUTO_DOCTYPES nhung CHI tu dong khi da len co rieng (moc
     site_config ec_esign_contract_auto_cancel_since + [ec_esign_auto_cancel_doctypes hoac mot
     lenh SM huy hop dong da xac minh]); co BAT KY ai da ky (ke ca doi tac) -> khong huy; doc lai
     cong ngay truoc lenh huy. DNTT giu luat cu (chi chan khi moi nguoi da ky).
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_PLAT = os.path.join(_APP, "ecentric_workspace", "platform")


def _read(*p):
    with io.open(os.path.join(_PLAT, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn_src(src, name):
    tree = ast.parse(src)
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n), n
    raise AssertionError("khong thay ham " + name)


class _D(dict):
    __getattr__ = dict.get


def _swap_modules(mods):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)

    def restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return restore


# ============================================================== A. docconvert
CTR_DT = "EC Contract Review Request"
TOKEN = "tok-SECRET-123"
DOCX = b"PK\x03\x04" + b"noi-dung-CCCD-012345678901" * 10
PDF = b"%PDF-1.7\n...pdf..."


class _R(object):
    def __init__(self, code, data=None, content=b""):
        self.status_code, self._d, self.content = code, data, content

    def json(self):
        if self._d is None:
            raise ValueError("no json")
        return self._d


class _Http(object):
    """Transport gia ghi lai moi lenh."""

    def __init__(self, **kw):
        self.calls, self.kw = [], kw

    def _rec(self, method, url, **k):
        self.calls.append((method, url, k))

    def put(self, url, data=None, headers=None, timeout=None):
        self._rec("PUT", url, data=data, headers=headers, timeout=timeout)
        if "uploadUrl" in url or url.startswith("https://up.example"):
            last = url and data is not None and self.kw.get("last_chunk_check", True)
            return _R(self.kw.get("chunk_code", 202), {"id": "ITEM-L"} if last else {})
        if self.kw.get("put_raise"):
            raise IOError("network down")
        return _R(self.kw.get("put_code", 201), {} if self.kw.get("noid") else {"id": "ITEM-1"})

    def post(self, url, json=None, headers=None, timeout=None):
        self._rec("POST", url, json=json, headers=headers, timeout=timeout)
        if url.endswith("createUploadSession"):
            return _R(200, {"uploadUrl": "https://up.example/sess?x=1"})
        if url.endswith("permanentDelete"):
            return _R(self.kw.get("perm_code", 204))
        return _R(404)

    def get(self, url, headers=None, timeout=None, allow_redirects=None):
        self._rec("GET", url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
        return _R(self.kw.get("get_code", 200), data=self.kw.get("listing"),
                  content=self.kw.get("pdf", PDF))

    def delete(self, url, headers=None, timeout=None):
        self._rec("DELETE", url, headers=headers, timeout=timeout)
        return _R(self.kw.get("del_code", 204))


def _load_docconvert(conf, token_fail=False):
    w = {"errors": []}
    fk = types.ModuleType("frappe")
    fk.conf = _D(conf)
    fk.log_error = lambda *a, **k: w["errors"].append(a)
    fk.get_traceback = lambda: "tb"
    w["todos"] = []
    fk.db = types.SimpleNamespace(exists=lambda dt, f=None: any(
        t["description"] == (f or {}).get("description") for t in w["todos"]))

    class _Doc(object):
        def __init__(self, d):
            self.d = d

        def insert(self, **k):
            w["todos"].append(self.d)
            return self
    fk.get_doc = lambda d: _Doc(d)
    sp = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
    sp.GRAPH = "https://graph.microsoft.com/v1.0"
    sp.SITE_ID = "SITE-OP"

    def get_app_token():
        if token_fail:
            raise RuntimeError("aad down " + TOKEN)
        return TOKEN
    sp.get_app_token = get_app_token
    wr = types.ModuleType("ecentric_workspace.weekly_report")
    wr.sharepoint = sp
    restore = _swap_modules({"frappe": fk, "ecentric_workspace.weekly_report": wr,
                             "ecentric_workspace.weekly_report.sharepoint": sp})
    m = types.ModuleType("_docconvert")
    exec(compile(_read("docconvert.py"), "docconvert.py", "exec"), m.__dict__)
    return m, w, restore


class TestDocconvert(unittest.TestCase):
    def mk(self, conf=None, **kw):
        m, w, restore = _load_docconvert({"ec_docconvert": conf} if conf is not None else {},
                                         **kw)
        self.addCleanup(restore)
        return m, w

    def test_chua_cau_hinh_thi_tu_choi_khong_goi_mang(self):
        for conf in (None, {}, {"folder": "x"}, {"allow_default_site": 0}):
            m, w = self.mk(conf)
            http = _Http()
            with self.assertRaises(m.ConvertError) as cm:
                m.docx_to_pdf(DOCX, "HD.docx", http=http, token=TOKEN)
            self.assertIn("Chưa cấu hình", str(cm.exception))
            self.assertEqual(http.calls, [], conf)
            self.assertFalse(m.is_configured())

    def test_khong_phai_docx_hoac_rong_thi_tu_choi_truoc(self):
        m, w = self.mk({"drive_id": "D1"})
        for bad in (b"", b"%PDF-1.4 abc", b"\xd0\xcf\x11\xe0 old .doc"):
            http = _Http()
            with self.assertRaises(m.ConvertError):
                m.docx_to_pdf(bad, "x.docx", http=http, token=TOKEN)
            self.assertEqual(http.calls, [])

    def test_qua_lon_thi_tu_choi(self):
        m, w = self.mk({"drive_id": "D1"})
        http = _Http()
        with self.assertRaises(m.ConvertError):
            m.docx_to_pdf(b"PK" + b"0" * (m.MAX_BYTES), "x.docx", http=http, token=TOKEN)
        self.assertEqual(http.calls, [])

    def test_tep_nho_put_get_xoa_vinh_vien(self):
        m, w = self.mk({"drive_id": "D1", "folder": "_tam"})
        http = _Http()
        out = m.docx_to_pdf(DOCX, "HD KOL Nguyen Van A.docx", http=http, token=TOKEN)
        self.assertEqual(out, PDF)
        self.assertEqual([c[0] for c in http.calls], ["PUT", "GET", "POST"])
        put, get, dele = http.calls
        base = "https://graph.microsoft.com/v1.0/drives/D1"
        self.assertTrue(put[1].startswith(base + "/root:/_tam/"))
        self.assertTrue(put[1].endswith(".docx:/content"))
        self.assertNotIn("Nguyen", put[1], "ten tep tam ngau nhien - khong lo ten hop dong")
        self.assertEqual(put[2]["data"], DOCX)
        self.assertEqual(put[2]["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertTrue(put[2]["timeout"])
        self.assertEqual(get[1], base + "/items/ITEM-1/content?format=pdf")
        self.assertTrue(get[2]["allow_redirects"], "theo 302 toi URL tai ve")
        self.assertEqual(dele[1], base + "/items/ITEM-1/permanentDelete")
        self.assertEqual(w["errors"], [])

    def test_site_id_va_allow_default_site(self):
        m, w = self.mk({"site_id": "S9"})
        http = _Http()
        m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
        self.assertTrue(http.calls[0][1].startswith(
            "https://graph.microsoft.com/v1.0/sites/S9/drive/root:/"))
        m, w = self.mk({"allow_default_site": 1})
        http = _Http()
        m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
        self.assertIn("/sites/SITE-OP/drive/root:/", http.calls[0][1])

    def test_ket_qua_khong_phai_pdf_van_xoa_tep_tam(self):
        m, w = self.mk({"drive_id": "D1"})
        http = _Http(pdf=b"<html>error</html>")
        with self.assertRaises(m.ConvertError) as cm:
            m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
        self.assertIn("không phải PDF", str(cm.exception))
        self.assertTrue(http.calls[-1][1].endswith("/items/ITEM-1/permanentDelete"))

    def test_chuyen_hong_http_van_xoa_va_khong_lo_token(self):
        m, w = self.mk({"drive_id": "D1"})
        http = _Http(get_code=500)
        with self.assertRaises(m.ConvertError) as cm:
            m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
        msg = str(cm.exception)
        self.assertIn("HTTP 500", msg)
        self.assertNotIn(TOKEN, msg)
        self.assertNotIn("CCCD", msg)
        self.assertTrue(http.calls[-1][1].endswith("/permanentDelete"))

    def test_tai_len_hong_xoa_theo_duong_dan(self):
        # QC M1: tra loi mat / loi mang sau khi Graph co the da ghi tep -> xoa theo DUONG DAN.
        m, w = self.mk({"drive_id": "D1", "folder": "_tam"})
        for kw in ({"put_code": 403}, {"put_raise": True}, {"noid": True}):
            http = _Http(**kw)
            with self.assertRaises(m.ConvertError):
                m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
            self.assertEqual([c[0] for c in http.calls], ["PUT", "POST"], kw)
            put, dele = http.calls
            self.assertEqual(dele[1], put[1][:-len("/content")] + "/permanentDelete", kw)
            self.assertIn("/root:/_tam/", dele[1])
        for err in w["errors"]:
            self.assertNotIn("CCCD", repr(err), "khong ghi noi dung tep vao log")

    def test_xoa_vinh_vien_hong_thi_delete_thuong_va_error_log(self):
        m, w = self.mk({"drive_id": "D1"})
        http = _Http(perm_code=400)
        self.assertEqual(m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN), PDF)
        self.assertEqual([c[0] for c in http.calls], ["PUT", "GET", "POST", "DELETE"])
        self.assertEqual(len(w["errors"]), 1)
        m, w = self.mk({"drive_id": "D1"})
        http = _Http(perm_code=500, del_code=500)
        self.assertEqual(m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN), PDF,
                         "xoa hong khong lam hong ket qua")
        self.assertIn("KHÔNG xoá", w["errors"][-1][0])
        self.assertEqual(len(w["todos"]), 1, "bao ops bang ToDo")
        self.assertIn(m.TODO_MARKER, w["todos"][0]["description"])
        m.docx_to_pdf(DOCX, "a.docx", http=_Http(perm_code=500, del_code=500), token=TOKEN)
        self.assertEqual(len(w["todos"]), 1, "cung ma tep -> khong tao ToDo trung")

    def test_khuc_tai_hong_thi_huy_phien_va_xoa_theo_duong_dan(self):
        m, w = self.mk({"drive_id": "D1"})
        m.SIMPLE_UPLOAD_MAX = 100
        m.CHUNK = 327680
        http = _Http(chunk_code=500)
        with self.assertRaises(m.ConvertError):
            m.docx_to_pdf(b"PK" + b"x" * (327680 * 2), "a.docx", http=http, token=TOKEN)
        kinds = [c[0] for c in http.calls]
        self.assertEqual(kinds, ["POST", "PUT", "DELETE", "POST"])
        self.assertEqual(http.calls[2][1], "https://up.example/sess?x=1", "huy phien tai")
        self.assertNotIn("headers", {k for k, v in http.calls[2][2].items() if v},
                         "khong gui token toi uploadUrl")
        self.assertTrue(http.calls[3][1].endswith(".docx:/permanentDelete"))

    def test_qua_han_tong_thi_dung_va_van_xoa(self):
        m, w = self.mk({"drive_id": "D1"})
        ticks = iter([0, 0, 1000, 1000, 1000])
        m._now = lambda: next(ticks)
        http = _Http()
        with self.assertRaises(m.ConvertError) as cm:
            m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
        self.assertIn("quá lâu", str(cm.exception))
        self.assertEqual([c[0] for c in http.calls], ["PUT", "POST"], "khong GET; van xoa tep")
        self.assertTrue(http.calls[1][1].endswith("/items/ITEM-1/permanentDelete"))
        m, w = self.mk({"drive_id": "D1"})
        m.DEADLINE_SECONDS = 90
        http = _Http()
        m.docx_to_pdf(DOCX, "a.docx", http=http, token=TOKEN)
        for c in http.calls[:2]:
            self.assertLessEqual(c[2]["timeout"], m.TIMEOUT)

    def test_sweep_temp_chi_xoa_tep_cu_theo_gio_utc(self):
        import datetime
        m, w = self.mk({"drive_id": "D1", "folder": "_tam"})
        now = datetime.datetime.utcnow()
        iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
        listing = {"value": [
            {"id": "OLD", "createdDateTime": iso(now - datetime.timedelta(minutes=40))},
            {"id": "NEW", "createdDateTime": iso(now - datetime.timedelta(minutes=2))},
            {"id": "BAD", "createdDateTime": "khong-doc-duoc"},
            {"id": "NOTS"}]}
        http = _Http(listing=listing)
        self.assertEqual(m.sweep_temp(http=http, token=TOKEN), 1)
        self.assertEqual(http.calls[0][0], "GET")
        self.assertIn("/drives/D1/root:/_tam:/children", http.calls[0][1])
        dels = [c[1] for c in http.calls if c[0] == "POST"]
        self.assertEqual(dels, ["https://graph.microsoft.com/v1.0/drives/D1/items/OLD/"
                                "permanentDelete"])

    def test_sweep_temp_chua_cau_hinh_hoac_hong_khong_nem(self):
        m, w = self.mk(None)
        http = _Http()
        self.assertEqual(m.sweep_temp(http=http, token=TOKEN), 0)
        self.assertEqual(http.calls, [])
        m, w = self.mk({"drive_id": "D1"})
        self.assertEqual(m.sweep_temp(http=_Http(get_code=404), token=TOKEN), 0)
        self.assertEqual(m.sweep_temp(http=_Http(get_code=500), token=TOKEN), 0)
        self.assertEqual(len(w["errors"]), 1)

    def test_tep_lon_dung_upload_session_khong_gui_auth_toi_upload_url(self):
        m, w = self.mk({"drive_id": "D1"})
        m.SIMPLE_UPLOAD_MAX = 100
        m.CHUNK = 327680
        big = b"PK" + b"x" * (327680 * 2 + 5)
        http = _Http()
        self.assertEqual(m.docx_to_pdf(big, "a.docx", http=http, token=TOKEN), PDF)
        kinds = [(c[0], c[1].split("?")[0][-30:]) for c in http.calls]
        self.assertEqual(kinds[0][0], "POST")
        self.assertTrue(http.calls[0][1].endswith(":/createUploadSession"))
        chunks = [c for c in http.calls if c[0] == "PUT"]
        self.assertEqual(len(chunks), 3)
        total = len(big)
        self.assertEqual(chunks[0][2]["headers"]["Content-Range"], "bytes 0-327679/%d" % total)
        self.assertEqual(chunks[-1][2]["headers"]["Content-Range"],
                         "bytes 655360-%d/%d" % (total - 1, total))
        for c in chunks:
            self.assertNotIn("Authorization", c[2]["headers"])
        self.assertEqual(b"".join(c[2]["data"] for c in chunks), big)
        self.assertTrue(http.calls[-1][1].endswith("/items/ITEM-L/permanentDelete"))

    def test_khong_lay_duoc_token(self):
        m, w = self.mk({"drive_id": "D1"}, token_fail=True)
        http = _Http()
        with self.assertRaises(m.ConvertError) as cm:
            m.docx_to_pdf(DOCX, "a.docx", http=http)
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertEqual(http.calls, [])


class TestConvertApiSource(unittest.TestCase):
    def setUp(self):
        self.src = _read("esign", "api.py")
        self.seg, self.node = _fn_src(self.src, "convert_business_docx_to_pdf")

    def test_post_va_dung_target_chung(self):
        deco = ast.get_source_segment(self.src, self.node.decorator_list[0])
        self.assertIn('methods=["POST"]', deco)
        self.assertIn("_target(business_doctype=business_doctype", self.seg,
                      "chi loai phieu da cau hinh ky so - khong thanh cua sau doc DocType bat ky")

    def test_chi_nguoi_tao(self):
        self.assertIn("perms.assert_requester(business_doctype, business_name)", self.seg)
        self.assertLess(self.seg.index("assert_requester"), self.seg.index("get_content"))

    def test_tep_phai_dinh_kem_dung_phieu_va_la_docx(self):
        self.assertIn('"attached_to_doctype": business_doctype', self.seg)
        self.assertIn('"attached_to_name": business_name', self.seg)
        self.assertIn("endswith(DOCX_MIME_EXT)", self.seg)

    def test_pdf_rieng_tu_dinh_kem_cung_phieu(self):
        self.assertIn('"is_private": 1', self.seg)
        self.assertIn('"attached_to_doctype": business_doctype, "attached_to_name": business_name',
                      self.seg)
        self.assertIn('return {"file_url": new.file_url, "file_name": new.file_name}', self.seg)

    def test_khong_code_rieng_hop_dong_khong_dong_vao_goi_ky(self):
        code = "\n".join(ast.get_source_segment(self.src, b) for b in self.node.body[1:])
        for bad in ("Contract", "kol_", "pkgsvc", "add_file", "svc."):
            self.assertNotIn(bad, code, bad)

    def test_khong_nhan_tham_so_nguoi_dung(self):
        args = [a.arg for a in self.node.args.args]
        self.assertEqual(args, ["business_doctype", "business_name", "file_url"])


class _ApiErr(Exception):
    pass


def _load_convert_api(w):
    """Chay THAT convert_business_docx_to_pdf voi frappe gia (QC PR-J: kiem hanh vi, khong chi chuoi)."""
    for k, v in (("cache", {}), ("inserted", []), ("comments", []), ("convert_calls", []),
                 ("read", 0), ("calls", [])):
        w.setdefault(k, v)
    src = _read("esign", "api.py")
    seg, node = _fn_src(src, "convert_business_docx_to_pdf")

    def throw(msg, *a, **k):
        raise _ApiErr(msg)

    files = w.get("files", {
        "/private/files/HD.docx": _D(name="F1", file_name="HD KOL.docx",
                                     file_url="/private/files/HD.docx", file_size=2048,
                                     attached_to_doctype="EC Contract Review Request",
                                     attached_to_name="CTR-1", is_folder=0)})

    def get_value(dt, filters, fields=None, **k):
        if dt == "File":
            f = files.get(filters.get("file_url"))
            if not f:
                return None
            for key in ("attached_to_doctype", "attached_to_name", "is_folder"):
                if f.get(key) != filters.get(key):
                    return None
            return f
        if dt == "EC Approval Request":
            return w.get("ar_status", "Pending")
        return None

    class Cache(object):
        def set(self, key, val, nx=False, ex=None):
            w["calls"].append(("lock", key, ex))
            if nx and key in w["cache"]:
                return False
            w["cache"][key] = val
            return True

        def delete(self, key):
            w["calls"].append(("unlock", key))
            w["cache"].pop(key, None)

    class _FileDoc(object):
        def __init__(self, d=None):
            self.d = d or {}

        def get_content(self):
            w["read"] += 1
            w["calls"].append(("read", dict(w["cache"])))
            return DOCX

        def insert(self, **k):
            w["inserted"].append(self.d)
            self.file_url = "/private/files/" + self.d["file_name"]
            self.file_name = self.d["file_name"]
            return self

        def add_comment(self, kind, text):
            w["comments"].append(text)

    def get_doc(a, b=None):
        if isinstance(a, dict):
            return _FileDoc(a)
        return _FileDoc()

    fk = types.SimpleNamespace(throw=throw, cache=lambda: Cache(), get_doc=get_doc,
                               db=types.SimpleNamespace(get_value=get_value),
                               log_error=lambda *a, **k: None, get_traceback=lambda: "")

    class ConvertError(Exception):
        pass

    dc = types.ModuleType("dc")
    dc.MAX_BYTES, dc.DEADLINE_SECONDS, dc.ConvertError = 10 * 1024 * 1024, 90, ConvertError

    def docx_to_pdf(content, name):
        w["convert_calls"].append((content, name))
        if w.get("convert_fail"):
            raise ConvertError("Chuyển PDF thất bại ở bước chuyển đổi (HTTP 500) - thử lại sau.")
        return PDF
    dc.docx_to_pdf = docx_to_pdf
    rl = types.ModuleType("rl")
    rl.hit = lambda *a, **k: w["calls"].append(("ratelimit",))
    plat = types.ModuleType("ecentric_workspace.platform")
    plat.docconvert = dc
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.ratelimit = rl
    restore = _swap_modules({"ecentric_workspace.platform": plat,
                             "ecentric_workspace.platform.docconvert": dc,
                             "ecentric_workspace.platform.esign": root,
                             "ecentric_workspace.platform.esign.ratelimit": rl})

    def assert_requester(dt, name):
        w["calls"].append(("requester", dt, name))
        if w.get("not_requester"):
            raise _ApiErr("Chỉ người tạo phiếu")

    perms = types.SimpleNamespace(assert_requester=assert_requester,
                                  business_approval_request=lambda dt, n: w.get("ar", "AR-1"))
    g = {"frappe": fk, "_": lambda s: s, "perms": perms, "DOCX_MIME_EXT": ".docx",
         "_target": lambda business_doctype=None, business_name=None: (business_doctype,
                                                                         business_name)}
    exec(compile(seg, "api.convert_business_docx_to_pdf", "exec"), g)
    return g["convert_business_docx_to_pdf"], restore


class TestConvertApiBehaviour(unittest.TestCase):
    def call(self, file_url="/private/files/HD.docx", dt=CTR_DT, name="CTR-1", **w):
        fn, restore = _load_convert_api(w)
        self.addCleanup(restore)
        try:
            return fn(dt, name, file_url), w
        except _ApiErr as e:
            return e, w

    def test_thanh_cong_pdf_rieng_tu_cung_phieu_va_mo_khoa(self):
        r, w = self.call()
        self.assertEqual(r, {"file_url": "/private/files/HD KOL.pdf", "file_name": "HD KOL.pdf"})
        ins = w["inserted"][0]
        self.assertEqual((ins["is_private"], ins["attached_to_doctype"], ins["attached_to_name"],
                          ins["content"]), (1, CTR_DT, "CTR-1", PDF))
        self.assertEqual(w["convert_calls"], [(DOCX, "HD KOL.docx")])
        self.assertEqual(w["cache"], {}, "mo khoa sau khi xong")
        lock = [c for c in w["calls"] if c[0] == "lock"][0]
        self.assertEqual(lock[1], "esign:docx_to_pdf:%s:CTR-1" % CTR_DT)
        self.assertEqual(lock[2], 120)
        read = [c for c in w["calls"] if c[0] == "read"][0]
        self.assertTrue(read[1], "doc tep TRONG khoa")
        self.assertEqual(len(w["comments"]), 1)

    def test_khong_phai_nguoi_tao_dung_truoc_moi_thu(self):
        r, w = self.call(not_requester=True)
        self.assertIsInstance(r, _ApiErr)
        self.assertEqual((w["read"], w["inserted"], w["convert_calls"]), (0, [], []))

    def test_duong_dan_xau_tu_choi(self):
        for bad in ("/etc/passwd", "https://x/private/files/HD.docx", "../private/files/HD.docx",
                    "private/files/HD.docx"):
            r, w = self.call(file_url=bad)
            self.assertIn("Đường dẫn", str(r), bad)
            self.assertEqual(w["read"], 0)

    def test_tep_cua_phieu_khac_hoac_thu_muc_tu_choi(self):
        other = {"/private/files/HD.docx": _D(name="F1", file_name="HD.docx", file_size=1,
                                              file_url="/private/files/HD.docx",
                                              attached_to_doctype=CTR_DT,
                                              attached_to_name="CTR-2", is_folder=0)}
        r, w = self.call(files=other)
        self.assertIn("Không tìm thấy", str(r))
        folder = {"/files/Home": _D(name="F2", file_name="Home.docx", file_url="/files/Home",
                                    file_size=0, attached_to_doctype=CTR_DT,
                                    attached_to_name="CTR-1", is_folder=1)}
        r, w = self.call(file_url="/files/Home", files=folder)
        self.assertIn("Không tìm thấy", str(r))
        self.assertEqual(w["read"], 0)

    def test_khong_phai_docx_tu_choi(self):
        f = {"/files/a.doc": _D(name="F3", file_name="a.doc", file_url="/files/a.doc",
                                file_size=10, attached_to_doctype=CTR_DT,
                                attached_to_name="CTR-1", is_folder=0)}
        r, w = self.call(file_url="/files/a.doc", files=f)
        self.assertIn(".docx", str(r))
        self.assertEqual(w["read"], 0)

    def test_qua_10mb_tu_choi_truoc_khi_doc(self):
        f = {"/files/big.docx": _D(name="F4", file_name="big.docx", file_url="/files/big.docx",
                                   file_size=10 * 1024 * 1024 + 1, attached_to_doctype=CTR_DT,
                                   attached_to_name="CTR-1", is_folder=0)}
        r, w = self.call(file_url="/files/big.docx", files=f)
        self.assertIn("10 MB", str(r))
        self.assertEqual((w["read"], w["cache"]), (0, {}))

    def test_phieu_da_ket_thuc_tu_choi(self):
        for st in ("Approved", "Rejected", "Cancelled"):
            r, w = self.call(ar_status=st)
            self.assertIn("đã kết thúc", str(r), st)
            self.assertEqual(w["read"], 0)
        r, w = self.call(ar=None, ar_status="Approved")
        self.assertIsInstance(r, dict, "phieu chua co yeu cau duyet -> van chuyen duoc")

    def test_dang_chuyen_cung_phieu_thi_tu_choi_khong_mo_khoa_nguoi_khac(self):
        key = "esign:docx_to_pdf:%s:CTR-1" % CTR_DT
        r, w = self.call(cache={key: "1"})
        self.assertIn("đang được chuyển PDF", str(r))
        self.assertEqual(w["read"], 0)
        self.assertIn(key, w["cache"], "khong xoa khoa cua lan dang chay")

    def test_chuyen_hong_thi_bao_loi_va_van_mo_khoa(self):
        r, w = self.call(convert_fail=True)
        self.assertIn("HTTP 500", str(r))
        self.assertEqual((w["inserted"], w["cache"]), ([], {}))


class TestAssertRequester(unittest.TestCase):
    def _mk(self, requested_by, user, roles=()):
        fk = types.ModuleType("frappe")
        fk._ = lambda s: s

        class PermErr(Exception):
            pass
        fk.PermissionError = PermErr

        def throw(msg, exc=None):
            raise (exc or RuntimeError)(msg)
        fk.throw = throw
        fk.session = _D(user=user)
        fk.get_roles = lambda u=None: list(roles)
        fk.db = types.SimpleNamespace(has_column=lambda dt, c: True,
                                      get_value=lambda dt, n, f: requested_by)
        restore = _swap_modules({"frappe": fk})
        self.addCleanup(restore)
        m = types.ModuleType("_perms")
        exec(compile(_read("esign", "permissions.py"), "permissions.py", "exec"), m.__dict__)
        return m, PermErr

    def test_nguoi_tao_va_sm_qua(self):
        m, _e = self._mk("a@x", "a@x")
        m.assert_requester("EC Contract Review Request", "C-1")
        m, _e = self._mk("a@x", "sm@x", roles=("System Manager",))
        m.assert_requester("EC Contract Review Request", "C-1")

    def test_nguoi_khac_hoac_khong_co_nguoi_tao_bi_chan(self):
        for rb, u in (("a@x", "b@x"), (None, "b@x"), ("", "")):
            m, PermErr = self._mk(rb, u)
            with self.assertRaises(PermErr):
                m.assert_requester("EC Contract Review Request", "C-1")


# ============================================================== B. portal resend
class _NH(object):
    def __init__(self, w):
        self.w = w

    def plan_portal_step(self, dsr, state, profile, env, adapter=None, instance_id=None):
        self.w["plan_args"] = (state, profile, env, instance_id)
        return self.w.get("plan", {"mode": "transition", "config": {"transition_id": -2},
                                   "state_before": "S1", "to_state": "S2"})


def _load_portal_resend(w):
    w.setdefault("writes", [])
    w.setdefault("events", [])
    w.setdefault("retries", [])
    src = _read("esign", "api.py")
    seg, _n = _fn_src(src, "_authorize_portal_resend")

    def throw(msg, *a, **k):
        raise RuntimeError(msg)

    def get_value(dt, name, fields=None, **k):
        if dt == "EC Digital Signature Package":
            return _D(scts_document_id=w.get("doc", "DOC-1"), status="Active", profile="PROF")
        if dt == "EC Digital Signature Profile":
            return w.get("trust", 1)
        return None

    fk = types.SimpleNamespace(
        throw=throw, session=_D(user="sm@x"),
        db=types.SimpleNamespace(get_value=get_value,
                                 set_value=lambda *a: w["writes"].append(a)))

    class _Ad(object):
        def workflow_state_for_document(self, doc, uid):
            w["wf_args"] = (doc, uid)
            return (w.get("state", {"current_state_id": "S1"}), w.get("why"))

    nh = types.ModuleType("nh")
    nh.plan_portal_step = _NH(w).plan_portal_step
    pk = types.ModuleType("pk")
    pk.workflow_instance_id = lambda name: w.get("iid", "INST-1")
    pv = types.ModuleType("pv")
    pv.get_adapter = lambda s: _Ad()
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.next_handler = nh
    restore = _swap_modules({"ecentric_workspace.platform.esign": root,
                             "ecentric_workspace.platform.esign.next_handler": nh,
                             "ecentric_workspace.platform.esign.package": pk,
                             "ecentric_workspace.platform.esign.providers": pv})
    import datetime
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: w.get("now", datetime.datetime(2026, 11, 24, 12, 0, 0))
    fu.get_datetime = lambda v: v
    fu.add_to_date = lambda d, minutes=0, **k: d + datetime.timedelta(minutes=minutes)
    restore2 = _swap_modules({"frappe.utils": fu})
    g = {"frappe": fk, "_": lambda s: s, "PORTAL_RESEND_MIN_AGE": 10,
         "_settings_of": lambda d: _D(environment="Production"),
         "events": types.SimpleNamespace(emit=lambda et, **k: w["events"].append((et, k))),
         "svc": types.SimpleNamespace(retry_signature_request=lambda n: w["retries"].append(n)
                                      or {"queued": True})}
    exec(compile(seg, "api._authorize_portal_resend", "exec"), g)
    return g["_authorize_portal_resend"], lambda: (restore2(), restore())


class TestPortalResend(unittest.TestCase):
    DSR = _D(name="DSR-1", package="PKG-1", action="Approve", status="Manual Review",
             effective_scts_user_id="U-REQ", provider_state_before="", request_attempt=2)

    def run_(self, dsr=None, **w):
        fn, restore = _load_portal_resend(w)
        self.addCleanup(restore)
        return fn(dsr or self.DSR, "500 luc tao tai lieu, cong van o buoc khoi tao"), w

    def assertNoFlag(self, w):
        self.assertEqual((w["writes"], w["events"], w["retries"]), ([], [], []))

    def test_canh_dang_mo_thi_dat_co_ghi_vet_roi_retry(self):
        r, w = self.run_()
        self.assertEqual(r, {"queued": True})
        self.assertEqual(w["writes"], [("EC Digital Signature Request", "DSR-1",
                                        "resend_authorized", 1)])
        et, k = w["events"][0]
        self.assertEqual(et, "ResendAuthorized")
        self.assertEqual(k["request_meta"]["loai"], "portal_step")
        self.assertEqual(k["request_meta"]["transition_id"], -2)
        self.assertEqual(k["request_meta"]["current_state_id"], "S1")
        self.assertEqual(w["retries"], ["DSR-1"])
        self.assertEqual(w["wf_args"], ("DOC-1", "U-REQ"))
        self.assertEqual(w["plan_args"][3], "INST-1")

    def test_ke_hoach_khong_phai_transition_thi_tu_choi(self):
        for plan in ({"mode": "wait", "reason": "not_at_step"},
                     {"mode": "blocked", "reason": "edge_closed"}, {}):
            w2 = {"plan": plan}
            fn2, restore2 = _load_portal_resend(w2)
            self.addCleanup(restore2)
            with self.assertRaises(RuntimeError):
                fn2(self.DSR, "x")
            self.assertNoFlag(w2)

    def test_cong_da_roi_buoc_thi_tu_choi(self):
        dsr = _D(self.DSR, provider_state_before="S1|S2")
        w = {"state": {"current_state_id": "S2"}}
        fn, restore = _load_portal_resend(w)
        self.addCleanup(restore)
        with self.assertRaises(RuntimeError) as cm:
            fn(dsr, "x")
        self.assertIn("đã rời bước", str(cm.exception))
        self.assertNoFlag(w)

    def test_cong_dung_buoc_dau_cua_chuoi_S1_S2_thi_cho(self):
        dsr = _D(self.DSR, provider_state_before="S1|S2")
        r, w = self.run_(dsr=dsr, state={"current_state_id": "S1"})
        self.assertEqual(r, {"queued": True})
        self.assertEqual(w["retries"], ["DSR-1"])

    def test_vua_thu_duoi_10_phut_thi_tu_choi(self):
        import datetime
        now = datetime.datetime(2026, 11, 24, 12, 0, 0)
        for field in ("modified", "accepted_at"):
            dsr = _D(self.DSR, **{field: now - datetime.timedelta(minutes=4)})
            w = {"now": now}
            fn, restore = _load_portal_resend(w)
            self.addCleanup(restore)
            with self.assertRaises(RuntimeError) as cm:
                fn(dsr, "x")
            self.assertIn("10 phút", str(cm.exception))
            self.assertNoFlag(w)
            self.assertNotIn("wf_args", w, "chua hoi cong")
        dsr = _D(self.DSR, modified=now - datetime.timedelta(minutes=11))
        r, w = self.run_(dsr=dsr, now=now)
        self.assertEqual(r, {"queued": True})

    def test_khong_doc_duoc_cong_thi_tu_choi(self):
        w = {"state": None, "why": "scts_network_error"}
        fn, restore = _load_portal_resend(w)
        self.addCleanup(restore)
        with self.assertRaises(RuntimeError):
            fn(self.DSR, "x")
        self.assertNoFlag(w)

    def test_ho_so_khong_lay_buoc_tu_cong_hoac_chua_co_tai_lieu(self):
        for kw in ({"trust": 0}, {"doc": None}):
            w = dict(kw)
            fn, restore = _load_portal_resend(w)
            self.addCleanup(restore)
            with self.assertRaises(RuntimeError):
                fn(self.DSR, "x")
            self.assertNoFlag(w)


class TestAuthorizeResendThuTu(unittest.TestCase):
    def setUp(self):
        self.seg, _n = _fn_src(_read("esign", "api.py"), "authorize_resend")

    def test_sm_ly_do_manual_review_truoc_nhanh_approve(self):
        i_sm = self.seg.index("perms.assert_system_manager()")
        i_mr = self.seg.index('dsr.status != "Manual Review"')
        i_ap = self.seg.index('if dsr.action == "Approve":')
        self.assertLess(i_sm, i_mr)
        self.assertLess(i_mr, i_ap)
        self.assertIn("return _authorize_portal_resend(dsr, ly_do)", self.seg)

    def test_chan_ky_van_qua_kiem_chu_ky_cu(self):
        # DNTT / chan Sign: van hoi poll_status + verify_signed_result, chi 2 ly do "chua ky".
        for s in ("adapter.poll_status(pkg.scts_document_id)",
                  "SignatureProviderAdapter.verify_signed_result(doc_state, expected)",
                  'startswith("expected_signer_absent")', 'startswith("not_enough_signatures")'):
            self.assertIn(s, self.seg)


# ============================================================== C. auto-cancel hop dong
from ecentric_workspace.approval_center.tests.standalone import test_esign_cmc_huy_tai_lieu as H  # noqa: E402

CTR = "EC Contract Review Request"


class _State(object):
    def __init__(self, signers):
        self.status = "Đang xử lý"
        self.signers = signers
        self.identity = {"creator_email": "a@x"}


class TestHuyHopDong(H.Base):
    ARMED = {"ec_esign_contract_auto_cancel_since": "2026-11-25 09:00:00",
             "ec_esign_auto_cancel_doctypes": [CTR]}

    def test_hang_so(self):
        m, w = self.mk()
        self.assertIn(CTR, m.AUTO_DOCTYPES)
        self.assertNotIn(CTR, m.AUTO_SINCE_BY_DOCTYPE, "moc hop dong doc tu site_config")
        self.assertEqual(m.SEPARATELY_ARMED[CTR], "ec_esign_contract_auto_cancel_since")
        self.assertEqual(m.AUTO_SINCE, "2026-11-18 00:00:00", "DNTT giu moc cu")

    def test_len_co_hop_dong(self):
        m, w = self.mk()
        self.assertTrue(m.doctype_armed("EC Payment Request"))
        self.assertFalse(m.doctype_armed(CTR), "chua co moc -> chua tu dong")
        m, w = self.mk(conf={"ec_esign_auto_cancel_doctypes": [CTR]})
        self.assertFalse(m.doctype_armed(CTR), "co danh sach nhung thieu moc -> chua")
        m, w = self.mk(conf={"ec_esign_contract_auto_cancel_since": "2026-11-25 09:00:00"})
        self.assertFalse(m.doctype_armed(CTR), "co moc nhung chua SM huy that / chua liet ke")
        m, w = self.mk(conf=dict(self.ARMED))
        self.assertTrue(m.doctype_armed(CTR))
        m, w = self.mk(conf={"ec_esign_contract_auto_cancel_since": "2026-11-25 09:00:00",
                             "ec_esign_auto_cancel_doctypes": "EC Payment Request, " + CTR})
        self.assertTrue(m.doctype_armed(CTR), "chuoi phan cach dau phay")

    def test_len_co_bang_lenh_sm_huy_hop_dong_da_xac_minh(self):
        m, w = self.mk(conf={"ec_esign_contract_auto_cancel_since": "2026-11-25 09:00:00"})
        seen = {}

        def get_all(dt, filters=None, fields=None, **k):
            seen["evt"] = filters
            return [_D(package="PKG-SM")]

        def exists(dt, f=None, **k):
            seen["pkg"] = (dt, f)
            return w.get("sm_on_ctr", True)
        m.frappe.get_all, m.frappe.db.exists = get_all, exists
        self.assertTrue(m.doctype_armed(CTR))
        flat = repr(seen["evt"])
        self.assertIn("Cancelled", flat)
        self.assertIn(m.CODE + ":cancelled", flat)
        self.assertIn(m.SOURCE_SM, flat)
        self.assertEqual(seen["pkg"][1]["business_doctype"], CTR)
        w["sm_on_ctr"] = False
        self.assertFalse(m.doctype_armed(CTR), "SM chi huy DNTT -> hop dong chua len co")

    def test_hop_dong_chua_ai_ky_thi_huy(self):
        m, w = self.mk(bdt=CTR, signed=0, total=3)
        r = m.cancel_one("PKG-1", dry_run=False, source="auto_cancel")
        self.assertEqual(r["result"], "cancelled")
        self.assertEqual(len(w["cancels"]), 1)

    def test_hop_dong_co_nguoi_ky_thi_khong_huy(self):
        m, w = self.mk(bdt=CTR, signed=1, total=3)
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(r["result"], "stop")
        self.assertEqual(r["reason"], "signed_on_portal:1/3")
        self.assertEqual((w["cancels"], self.marks(w)), ([], []))

    def test_doi_tac_da_ky_ghi_ro_external(self):
        m, w = self.mk(bdt=CTR)
        st = _State([{"status": "pending"}, {"status": "signed", "is_external": True}])
        m.get_adapter = lambda s: types.SimpleNamespace(
            poll_status=lambda d: st, use_user_token=lambda t: None,
            cancel_document=lambda *a: w["cancels"].append(a))
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(r["reason"], "signed_on_portal:1/2:external")
        self.assertEqual(w["cancels"], [])

    def test_chay_thu_hop_dong_co_nguoi_ky_cung_stop(self):
        m, w = self.mk(bdt=CTR, signed=2, total=3)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=True)["result"], "stop")

    def test_dntt_van_luat_cu_mot_nguoi_ky_van_huy(self):
        m, w = self.mk(signed=1, total=5)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["result"], "cancelled")

    def test_goi_superseded_giu_luat_pr_g(self):
        # Ban sua (PR-G) chi chan chu ky ERP KHONG biet - luat chat chi cho phieu tu choi / huy.
        src = _read("esign", "provider_cancel.py")
        self.assertIn('if pkg.status != "Superseded" and signed and pkg.business_doctype in '
                      'STRICT_ANY_SIGNED:', src)

    def test_sweep_hop_dong_chua_len_co_thi_khong_lay(self):
        m, w = self.mk()
        m.sweep()
        by_dt = {f["reference_doctype"]: f["completed_at"] for f in w["ar_filters"]}
        self.assertEqual(by_dt, {"EC Payment Request": [">=", "2026-11-18 00:00:00"]})

    def test_sweep_hop_dong_da_len_co_dung_moc_site_config(self):
        m, w = self.mk(conf=dict(self.ARMED))
        m.sweep()
        by_dt = {f["reference_doctype"]: f["completed_at"] for f in w["ar_filters"]}
        self.assertEqual(by_dt, {"EC Payment Request": [">=", "2026-11-18 00:00:00"],
                                 CTR: [">=", "2026-11-25 09:00:00"]})

    def test_doi_tac_ky_giua_hai_lan_doc_thi_khong_huy(self):
        m, w = self.mk(bdt=CTR, signed=0, total=2)
        states = [_State([{"status": "pending"}, {"status": "pending"}]),
                  _State([{"status": "pending"}, {"status": "signed", "is_external": True}])]
        polls = []

        def poll(d):
            polls.append(d)
            return states[min(len(polls), 2) - 1]
        m.get_adapter = lambda s: types.SimpleNamespace(
            poll_status=poll, use_user_token=lambda t: types.SimpleNamespace(
                poll_status=poll, cancel_document=lambda *a: w["cancels"].append(a)),
            cancel_document=lambda *a: w["cancels"].append(a))
        r = m.cancel_one("PKG-1", dry_run=False, source="auto_cancel")
        self.assertEqual((r["result"], r["reason"]), ("stop", "changed_before_cancel"))
        self.assertEqual(w["cancels"], [])
        self.assertGreaterEqual(len(polls), 2, "doc lai cong ngay truoc lenh huy")

    def test_dntt_khong_doc_lai_truoc_huy(self):
        m, w = self.mk(signed=1, total=5)
        m.cancel_one("PKG-1", dry_run=False)
        n_dntt = len(w["polls"])
        m, w = self.mk(bdt=CTR, signed=0, total=5)
        m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(len(w["polls"]), n_dntt + 1)

    def test_lenh_sm_gom_ca_truoc_moc(self):
        m, w = self.mk()
        m.candidates(include_before=True)
        for f in w["ar_filters"]:
            self.assertNotIn("completed_at", f)


if __name__ == "__main__":
    unittest.main()
