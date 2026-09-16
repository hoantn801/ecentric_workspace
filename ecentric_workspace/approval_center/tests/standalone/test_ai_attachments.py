# Copyright (c) 2026, eCentric and contributors
"""Cong doc tep dinh kem cua AI dien ho (G2). Chay code THAT voi frappe gia.

PHEP KIEM DAT NHAT O DAY LA `test_tep_cua_nguoi_khac_bi_tu_choi`. Trinh duyet gui len mot
chuoi `/private/files/<ten>`; neu server cu the ma doc thi bat ky nguoi dung da dang nhap nao
cung lay duoc noi dung tep cua nguoi khac - AI doc ho roi tra ra man hinh duoi dang "trich dan
nguon". Do la mot duong ro du lieu hoan chinh ma khong co dong SQL nao sai, nen no phai co
test rieng va phai chet khi cong bi go.

Moi luat co mot mau DAT va mot mau TRUOT (A56).
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(
    _HERE, "..", "..", "shared", "integrations", "ai_attachments.py"))

TOI = "hoan.tran@ecentric.vn"
NGUOI_KHAC = "ai.do@ecentric.vn"


def _load(rows=None, perm=True, content=None):
    """rows: {file_url: [row, ...]}   content: {File.name: bytes}"""
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=TOI)
    _rows = dict(rows or {})
    _content = dict(content or {})

    def _get_all(dt, filters=None, fields=None, **kw):
        assert dt == "File"
        return [dict(r) for r in _rows.get((filters or {}).get("file_url"), [])]
    fk.get_all = _get_all

    def _has_permission(dt, doc=None, ptype=None, user=None):
        return perm(dt, doc, user) if callable(perm) else bool(perm)
    fk.has_permission = _has_permission

    class _FileDoc(object):
        def __init__(self, name):
            self.name = name
        def get_content(self):
            if self.name not in _content:
                raise IOError("khong doc duoc")
            return _content[self.name]
    fk.get_doc = lambda dt, name: _FileDoc(name)

    # `ecentric_workspace.gemini_api` duoc import BEN TRONG `collect`; test luon truyen
    # `uploader` nen duong that khong bao gio chay - nhung import van phai giai duoc.
    pkg = types.ModuleType("ecentric_workspace")
    pkg.__path__ = []
    gem = types.ModuleType("ecentric_workspace.gemini_api")
    gem.upload_file_bytes = lambda *a, **k: {"success": False, "error": "khong duoc goi"}
    pkg.gemini_api = gem

    mods = {"frappe": fk, "ecentric_workspace": pkg,
            "ecentric_workspace.gemini_api": gem}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_ai_attachments_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "ai_attachments.py", "exec"), m.__dict__)
        m._fk, m._mods = fk, mods
        return m, fk
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _run(m, fn):
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


def _row(url, name, owner=TOI, size=1000, dt=None, dn=None):
    return {"name": "FILE-" + name, "file_name": name, "file_url": url, "owner": owner,
            "file_size": size, "attached_to_doctype": dt, "attached_to_name": dn,
            "is_folder": 0}


def _uploader(log=None, ok=True):
    def up(data, filename, mime, **kw):
        if log is not None:
            log.append({"filename": filename, "mime": mime, "bytes": len(data)})
        if not ok:
            return {"success": False, "error": "gia lap hong"}
        return {"success": True, "uri": "files/" + filename, "mime_type": mime}
    return up


def _reasons(rejected):
    return dict((r["file"], r["reason"]) for r in rejected)


# ------------------------------------------------------------------ mime ---

class TestMime(unittest.TestCase):
    def setUp(self):
        self.m, _ = _load()

    def test_pdf_va_anh_duoc_nhan(self):
        self.assertEqual(self.m.mime_for("hoa-don.PDF")[0], "application/pdf")
        self.assertEqual(self.m.mime_for("anh.jpeg")[0], "image/jpeg")
        self.assertEqual(self.m.mime_for("ghi-chu.txt")[0], "text/plain")

    def test_office_bi_tu_choi_voi_ly_do_RIENG(self):
        # Ly do rieng vi cau tra loi khac han: "xuat ra PDF" chu khong phai "khong doc duoc".
        mime, why = self.m.mime_for("hop-dong.docx")
        self.assertIsNone(mime)
        self.assertEqual(why, "office")
        self.assertIn("PDF", self.m.LY_DO["office"])

    def test_kieu_la_bi_tu_choi(self):
        self.assertEqual(self.m.mime_for("chay.exe")[1], "bad_type")
        self.assertEqual(self.m.mime_for("khong-co-duoi")[1], "bad_type")

    def test_ext_of(self):
        self.assertEqual(self.m.ext_of("/private/files/A.B.pdf"), "pdf")
        self.assertEqual(self.m.ext_of("khongduoi"), "")


# ------------------------------------------------------------- cong quyen ---

class TestQuyenDoc(unittest.TestCase):
    def test_chinh_minh_tai_len_thi_duoc(self):
        m, _ = _load()
        self.assertTrue(_run(m, lambda: m.may_read(_row("/private/files/a.pdf", "a.pdf"))))

    def test_tep_mo_coi_cua_nguoi_khac_thi_KHONG(self):
        m, _ = _load()
        row = _row("/private/files/a.pdf", "a.pdf", owner=NGUOI_KHAC)
        self.assertFalse(_run(m, lambda: m.may_read(row)))

    def test_tep_gan_vao_ho_so_doc_duoc_thi_duoc(self):
        m, _ = _load(perm=True)
        row = _row("/private/files/a.pdf", "a.pdf", owner=NGUOI_KHAC,
                   dt="EC Payment Request", dn="EC-PAYR-1")
        self.assertTrue(_run(m, lambda: m.may_read(row)))

    def test_tep_gan_vao_ho_so_KHONG_doc_duoc_thi_khong(self):
        m, _ = _load(perm=False)
        row = _row("/private/files/a.pdf", "a.pdf", owner=NGUOI_KHAC,
                   dt="EC Payment Request", dn="EC-PAYR-1")
        self.assertFalse(_run(m, lambda: m.may_read(row)))

    def test_pick_readable_chon_dung_dong_doc_duoc(self):
        # Mot file_url co the ung voi nhieu dong File (Frappe gop theo noi dung). Lay dai
        # mot dong bat ky roi hoi quyen tren dong do = nguoi CO quyen van bi tu choi.
        m, _ = _load(perm=False)
        rows = [_row("/private/files/a.pdf", "a.pdf", owner=NGUOI_KHAC),
                _row("/private/files/a.pdf", "a.pdf", owner=TOI)]
        row, existed = _run(m, lambda: m.pick_readable(rows))
        self.assertIsNotNone(row)
        self.assertEqual(row["owner"], TOI)
        self.assertTrue(existed)

    def test_pick_readable_phan_biet_khong_co_voi_khong_duoc(self):
        m, _ = _load(perm=False)
        self.assertEqual(_run(m, lambda: m.pick_readable([])), (None, False))
        rows = [_row("/private/files/a.pdf", "a.pdf", owner=NGUOI_KHAC)]
        row, existed = _run(m, lambda: m.pick_readable(rows))
        self.assertIsNone(row)
        self.assertTrue(existed)


# ----------------------------------------------------------------- collect ---

class TestCollect(unittest.TestCase):
    def test_duong_thuan_loi(self):
        url = "/private/files/hoa-don.pdf"
        m, _ = _load(rows={url: [_row(url, "hoa-don.pdf")]},
                     content={"FILE-hoa-don.pdf": b"%PDF-1.7 noi dung"})
        log = []
        parts, bad = _run(m, lambda: m.collect([url], uploader=_uploader(log)))
        self.assertEqual(bad, [])
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["mime_type"], "application/pdf")
        self.assertEqual(parts[0]["display_name"], "hoa-don.pdf")
        self.assertEqual(log[0]["mime"], "application/pdf")

    def test_tep_cua_nguoi_khac_bi_tu_choi(self):
        # Phep kiem dat nhat cua module. Xem docstring dau file.
        url = "/private/files/luong-sep.pdf"
        m, _ = _load(rows={url: [_row(url, "luong-sep.pdf", owner=NGUOI_KHAC)]},
                     content={"FILE-luong-sep.pdf": b"%PDF bi mat"}, perm=False)
        log = []
        parts, bad = _run(m, lambda: m.collect([url], uploader=_uploader(log)))
        self.assertEqual(parts, [])
        self.assertEqual(_reasons(bad), {"luong-sep.pdf": "no_permission"})
        # Va khong duoc doc MOT BYTE nao len Gemini.
        self.assertEqual(log, [])

    def test_khong_tim_thay_khac_voi_khong_co_quyen(self):
        m, _ = _load(rows={})
        parts, bad = _run(m, lambda: m.collect(["/private/files/khong-co.pdf"],
                                               uploader=_uploader()))
        self.assertEqual(_reasons(bad), {"khong-co.pdf": "not_found"})
        self.assertEqual(parts, [])

    def test_duong_dan_ngoai_kho_bi_chan(self):
        m, _ = _load(rows={})
        for url in ("../../etc/passwd", "https://vidu.com/a.pdf", "/app/file/x"):
            parts, bad = _run(m, lambda u=url: m.collect([u], uploader=_uploader()))
            self.assertEqual(parts, [], url)
            self.assertEqual(bad[0]["reason"], "not_found", url)

    def test_office_bi_bo_nhung_tep_khac_van_chay(self):
        u1, u2 = "/private/files/hd.docx", "/private/files/hd.pdf"
        m, _ = _load(rows={u1: [_row(u1, "hd.docx")], u2: [_row(u2, "hd.pdf")]},
                     content={"FILE-hd.docx": b"PK...", "FILE-hd.pdf": b"%PDF"})
        parts, bad = _run(m, lambda: m.collect([u1, u2], uploader=_uploader()))
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["display_name"], "hd.pdf")
        self.assertEqual(_reasons(bad), {"hd.docx": "office"})

    def test_qua_tran_so_tep(self):
        rows, cont, urls = {}, {}, []
        for i in range(m_max := 7):
            u = "/private/files/t%d.pdf" % i
            urls.append(u)
            rows[u] = [_row(u, "t%d.pdf" % i)]
            cont["FILE-t%d.pdf" % i] = b"%PDF"
        m, _ = _load(rows=rows, content=cont)
        parts, bad = _run(m, lambda: m.collect(urls, uploader=_uploader()))
        self.assertEqual(len(parts), m.MAX_FILES)
        self.assertEqual(len(bad), m_max - m.MAX_FILES)
        self.assertTrue(all(r["reason"] == "over_cap" for r in bad))

    def test_file_size_noi_doi_van_bi_bat(self):
        # `file_size` la thu do TIN, khong phai thu do BIET: mot dong File co the ghi 10 byte
        # trong khi tep tren dia la 30MB. Chi kiem o metadata thi cong nay vo dung.
        url = "/private/files/to.pdf"
        m, _ = _load(rows={url: [_row(url, "to.pdf", size=10)]},
                     content={"FILE-to.pdf": b"x" * (11 * 1024 * 1024)})
        parts, bad = _run(m, lambda: m.collect([url], uploader=_uploader()))
        self.assertEqual(parts, [])
        self.assertEqual(_reasons(bad), {"to.pdf": "too_big"})

    def test_tran_tong_dung_luong(self):
        rows, cont, urls = {}, {}, []
        for i in range(4):
            u = "/private/files/b%d.pdf" % i
            urls.append(u)
            rows[u] = [_row(u, "b%d.pdf" % i)]
            cont["FILE-b%d.pdf" % i] = b"x" * (9 * 1024 * 1024)
        m, _ = _load(rows=rows, content=cont)
        parts, bad = _run(m, lambda: m.collect(urls, uploader=_uploader()))
        self.assertEqual(len(parts), 2)              # 9 + 9 = 18MB, them nua thi qua 25MB
        self.assertTrue(all(r["reason"] == "total_too_big" for r in bad))

    def test_tai_len_hong_khong_lam_hong_ca_luot(self):
        u1, u2 = "/private/files/a.pdf", "/private/files/b.pdf"
        m, _ = _load(rows={u1: [_row(u1, "a.pdf")], u2: [_row(u2, "b.pdf")]},
                     content={"FILE-a.pdf": b"%PDF", "FILE-b.pdf": b"%PDF"})
        lan = {"n": 0}
        def up(data, filename, mime, **kw):
            lan["n"] += 1
            if lan["n"] == 1:
                return {"success": False, "error": "gia lap hong"}
            return {"success": True, "uri": "files/" + filename, "mime_type": mime}
        parts, bad = _run(m, lambda: m.collect([u1, u2], uploader=up))
        self.assertEqual(len(parts), 1)
        self.assertEqual(_reasons(bad), {"a.pdf": "upload_failed"})

    def test_het_ngan_sach_thoi_gian_thi_dung_lai(self):
        rows, cont, urls = {}, {}, []
        for i in range(3):
            u = "/private/files/c%d.pdf" % i
            urls.append(u)
            rows[u] = [_row(u, "c%d.pdf" % i)]
            cont["FILE-c%d.pdf" % i] = b"%PDF"
        m, _ = _load(rows=rows, content=cont)
        dong_ho = {"t": 0.0}
        def now():
            dong_ho["t"] += 30.0        # moi lan hoi gio la tron 30 giay
            return dong_ho["t"]
        parts, bad = _run(m, lambda: m.collect(urls, uploader=_uploader(), now=now))
        self.assertTrue(len(parts) < 3)
        self.assertTrue(any(r["reason"] == "budget" for r in bad))

    def test_tep_rong_bi_bo(self):
        url = "/private/files/rong.pdf"
        m, _ = _load(rows={url: [_row(url, "rong.pdf")]}, content={"FILE-rong.pdf": b""})
        parts, bad = _run(m, lambda: m.collect([url], uploader=_uploader()))
        self.assertEqual(_reasons(bad), {"rong.pdf": "empty"})

    def test_noi_dung_str_duoc_doi_ve_bytes(self):
        # `File.get_content()` tra str khi noi dung giai ma duoc utf-8 (tep .txt).
        url = "/private/files/ghi-chu.txt"
        m, _ = _load(rows={url: [_row(url, "ghi-chu.txt")]},
                     content={"FILE-ghi-chu.txt": u"noi dung tieng Viet cho de"})
        log = []
        parts, bad = _run(m, lambda: m.collect([url], uploader=_uploader(log)))
        self.assertEqual(bad, [])
        self.assertEqual(len(parts), 1)
        self.assertTrue(log[0]["bytes"] > 0)


class TestPromptBlock(unittest.TestCase):
    def test_rong_khi_khong_co_tep(self):
        m, _ = _load()
        self.assertEqual(m.prompt_block([]), "")

    def test_liet_ke_ten_tep(self):
        m, _ = _load()
        out = m.prompt_block([{"display_name": "hoa-don.pdf"}, {"display_name": "hd.pdf"}])
        self.assertIn("hoa-don.pdf", out)
        self.assertIn("hd.pdf", out)
        self.assertIn("Tep 2", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
