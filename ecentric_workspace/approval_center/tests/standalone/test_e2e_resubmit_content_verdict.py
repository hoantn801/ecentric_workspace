# Copyright (c) 2026, eCentric and contributors
"""E2E vong doi: tra lai -> bo sung chung tu -> gui lai (lifecycle.on_request_reopened).

Ba ket cuc cua mot lan "Gui lai" khi da co goi ky dong bang:

  * `unchanged`  - chi dinh kem THEM bang chung: di tiep, KHONG tao phien ban goi moi,
                   KHONG bat ai ky lai (nguoi goi phia tren se khong goi sign_on_submit);
  * `changed`    - tai lieu CAN KY da doi: chan ngay, chua ghi gi, va thong bao phai chi
                   dung duong di ("Tu choi" + "Tao phieu moi") chu khong bo mac nguoi dung;
  * `unreadable` - khong doc duoc tep: chan, va noi dung su that ("khong kiem tra duoc"),
                   TUYET DOI khong doi lot thanh "da thay doi".

Chay HAM THAT voi frappe gia lap qua sys.modules (pattern test_esign_ops_inbox). Ma bam
duoc tinh bang hashing.py THAT tren noi dung tep that - khong dua dap so vao stub
(pattern test_retrieval_rounds_counts_failures: dung DONG DU LIEU, hoi ham that).

Bay da ne:
  * stub khong tra bua truong duoc hoi: get_value tren DocType nha lam duoc doi chieu
    fieldname voi file .json trong repo;
  * _D(dict) cho phep ca r["x"] lan r.x nhu frappe._dict;
  * verdict "changed"/"unreadable" nem loi TRUOC moi lenh ghi - recorder ghi lai moi
    set_value/insert de chung minh (nem sau khi ghi = rollback ca giao dich).
"""
import glob
import io
import json
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Throw(Exception):
    pass


# ---------------------------------------------------------------------------- #
# doi chieu truong voi DocType that (.json) - stub khong duoc tra bua
# ---------------------------------------------------------------------------- #
_STANDARD = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}


def _doctype_fields():
    out = {}
    for path in glob.glob(os.path.join(_ROOT, "*", "doctype", "*", "*.json")):
        try:
            doc = json.loads(io.open(path, encoding="utf-8").read())
        except ValueError:
            continue
        if doc.get("doctype") != "DocType" or not doc.get("name"):
            continue
        out[doc["name"]] = {f.get("fieldname") for f in doc.get("fields", [])
                            if f.get("fieldname")} | _STANDARD
    return out


_FIELDS = _doctype_fields()


def _assert_fields(doctype, fields):
    known = _FIELDS.get(doctype)
    if known is None:            # DocType loi cua Frappe (File, ToDo...) - khong co json local
        return
    if isinstance(fields, str):
        fields = [fields]
    for f in fields or []:
        if f == "*":
            continue
        assert f in known, "truong %r khong ton tai tren DocType %s" % (f, doctype)


# ---------------------------------------------------------------------------- #
# nap lifecycle.py THAT + hashing.py THAT, frappe gia lap
# ---------------------------------------------------------------------------- #
def _real_hashing():
    mod = types.ModuleType("hashing")
    exec(compile(_read("platform", "esign", "hashing.py"), "hashing.py", "exec"), mod.__dict__)
    return mod


_HASHING = _real_hashing()

PKG = "EC Digital Signature Package"


def _load_lifecycle(attachments, pkg_files, frozen_pkg=True, signed_count=0):
    """attachments: list dict {name,file_name,file_url,is_private,content|read_error}
    pkg_files: list dict theo dung bo truong cua package.package_files."""
    import sys

    recorder = {"writes": [], "events": [], "pkg_files_calls": [], "reads": []}
    by_name = {a["name"]: a for a in attachments}

    class _DB(object):
        @staticmethod
        def get_value(dt, filters, fields=None, order_by=None, as_dict=False, **kw):
            _assert_fields(dt, fields)
            if dt == PKG:
                if not frozen_pkg:
                    return None
                st = (filters or {}).get("status")
                assert isinstance(st, list) and st[0] == "in", \
                    "phai loc goi theo danh sach trang thai dong bang"
                return _D({"name": "PKG-1", "business_doctype": "EC Payment Request",
                           "business_name": "EC-PAYR-2026-00001"})
            return None

        @staticmethod
        def count(dt, filters=None):
            return signed_count

        @staticmethod
        def set_value(*a, **kw):
            recorder["writes"].append(("set_value", a))

    def get_all(dt, filters=None, fields=None, limit_page_length=None, **kw):
        assert dt == "File", "lifecycle chi duoc doc File o duong nay, thay: %r" % dt
        out = []
        for a in attachments:
            if (filters or {}).get("is_private") == 1 and not a.get("is_private"):
                continue
            out.append(_D({"name": a["name"], "file_name": a.get("file_name"),
                           "file_url": a.get("file_url")}))
        return out

    class _FileDoc(object):
        def __init__(self, row):
            self._row = row

        def get_content(self):
            recorder["reads"].append(self._row["name"])
            if self._row.get("read_error"):
                raise IOError("disk says no")
            return self._row["content"]

    def get_doc(dt, name=None):
        if isinstance(dt, dict):
            recorder["writes"].append(("insert", dt))
            return types.SimpleNamespace(insert=lambda **kw: None)
        assert dt == "File"
        return _FileDoc(by_name[name])

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = _DB
    frappe_mod.get_all = get_all
    frappe_mod.get_doc = get_doc
    frappe_mod._ = lambda s: s
    frappe_mod._dict = _D

    def _throw(msg, exc=None):
        raise _Throw(msg)

    frappe_mod.throw = _throw

    events_mod = types.ModuleType("events")
    events_mod.emit = lambda *a, **kw: recorder["events"].append((a, kw))

    package_mod = types.ModuleType("package")

    def package_files(pkg_name):
        recorder["pkg_files_calls"].append(pkg_name)
        return [_D(r) for r in pkg_files]

    package_mod.package_files = package_files
    # Ma nguon doc byte tep qua `pkgsvc.raw_file_bytes` (02/09) chu khong goi thang
    # `File.get_content()`, vi ham do tra `str` cho tep giai ma duoc. Ban gia van di qua
    # CUNG mot `_FileDoc`, nen bo dem `recorder['reads']` - thu bo test nay that su do -
    # van dem dung so lan doc tep.
    package_mod.raw_file_bytes = lambda name: get_doc("File", name).get_content()

    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.events = events_mod
    esign_pkg.hashing = _HASHING
    esign_pkg.package = package_mod

    saved = {}
    for k, v in (("frappe", frappe_mod),
                 ("ecentric_workspace.platform.esign", esign_pkg),
                 ("ecentric_workspace.platform.esign.events", events_mod),
                 ("ecentric_workspace.platform.esign.hashing", _HASHING),
                 ("ecentric_workspace.platform.esign.package", package_mod)):
        saved[k] = sys.modules.get(k)
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("platform", "esign", "lifecycle.py"), "lifecycle.py", "exec"), env)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return env, recorder


# noi dung tep that - sha duoc tinh bang hashing THAT, khong dua dap so vao stub
_PDF_A = b"%PDF-1.4 to trinh thanh toan goc"
_PDF_A2 = b"%PDF-1.4 to trinh thanh toan DA SUA SO TIEN"
_PDF_INVOICE = b"%PDF-1.4 hoa don bo sung theo yeu cau ke toan"
_SHA_A = _HASHING.sha256_bytes(_PDF_A)


def _pkg_row(sha=_SHA_A, requires_signature=1, name="DSF-1", file_name="to-trinh.pdf"):
    # dung DUNG bo truong package.package_files tra ve - khong bia truong
    return {"name": name, "file": "F-copy", "file_name": file_name, "idx_order": 1,
            "file_kind": None, "requires_signature": requires_signature,
            "is_supporting_document": 0 if requires_signature else 1,
            "share_with_partner": 0, "sha256": sha, "size_bytes": 100,
            "mime_type": "application/pdf", "is_pdf": 1, "scts_document_file_id": None}


def _att(name, fname, content, private=1, read_error=False):
    return {"name": name, "file_name": fname, "file_url": "/private/files/" + fname,
            "is_private": private, "content": content, "read_error": read_error}


class TestSupplementOnlyGoesForward(unittest.TestCase):
    """Tra lai -> dinh kem them hoa don -> gui lai: di tiep, KHONG ky lai."""

    def test_them_bang_chung_khong_lam_moi_goi_ky(self):
        env, rec = _load_lifecycle(
            attachments=[_att("F1", "to-trinh.pdf", _PDF_A),
                         _att("F2", "hoa-don.pdf", _PDF_INVOICE)],
            pkg_files=[_pkg_row()])
        out = env["on_request_reopened"]("AR-1")
        self.assertFalse(out["revised"], "khong duoc tao phien ban goi moi cho bang chung them")
        self.assertTrue(out.get("unchanged"), "phai bao ro noi dung ky KHONG doi")
        self.assertFalse(out["force_restart"])
        self.assertEqual(rec["writes"], [], "duong unchanged khong ghi gi ca")

    def test_khong_co_goi_dong_bang_thi_di_tiep_va_khong_dem_xia_toi_tep(self):
        env, rec = _load_lifecycle(attachments=[], pkg_files=[], frozen_pkg=False)
        out = env["on_request_reopened"]("AR-1")
        self.assertEqual(out, {"revised": False, "new_package": None, "force_restart": False})
        self.assertEqual(rec["pkg_files_calls"], [],
                         "khong co goi thi khong duoc doc danh sach tep cua goi")

    def test_tep_trung_url_chi_doc_noi_dung_mot_lan(self):
        # Frappe hay tao 2 dong File tro cung mot duong dan - doc lai la I/O thua
        a1 = _att("F1", "to-trinh.pdf", _PDF_A)
        a2 = dict(a1, name="F1b")
        env, rec = _load_lifecycle(attachments=[a1, a2], pkg_files=[_pkg_row()])
        out = env["on_request_reopened"]("AR-1")
        self.assertTrue(out.get("unchanged"))
        self.assertEqual(rec["reads"].count("F1") + rec["reads"].count("F1b"), 1,
                         "cung file_url phai doc dung MOT lan")


class TestChangedSignableBlocksWithDirections(unittest.TestCase):
    """Tra lai -> to trinh bi sua -> gui lai: CHAN, va thong bao chi dung duong di."""

    def test_chan_va_thong_bao_tro_tu_choi_va_tao_phieu_moi(self):
        env, rec = _load_lifecycle(
            attachments=[_att("F1", "to-trinh.pdf", _PDF_A2)],   # noi dung DA DOI
            pkg_files=[_pkg_row()])                              # goi khoa sha cua ban GOC
        with self.assertRaises(_Throw) as ctx:
            env["on_request_reopened"]("AR-1")
        msg = str(ctx.exception)
        self.assertIn("Từ chối", msg, "phai bao cap duyet bam Tu choi")
        self.assertIn("Tạo phiếu mới", msg, "phai chi duong 'Tao phieu moi tu phieu nay'")
        self.assertEqual(rec["writes"], [],
                         "phai tu choi TRUOC khi ghi bat cu gi - nem sau khi ghi la rollback "
                         "ca giao dich va goi Draft vua tao bien mat (bai hoc 31/08)")

    def test_xoa_mat_tep_da_ky_cung_la_da_doi(self):
        env, _rec = _load_lifecycle(
            attachments=[_att("F2", "hoa-don.pdf", _PDF_INVOICE)],  # to trinh bien mat
            pkg_files=[_pkg_row()])
        with self.assertRaises(_Throw) as ctx:
            env["on_request_reopened"]("AR-1")
        self.assertIn("Tạo phiếu mới", str(ctx.exception))


class TestUnreadableBlocksWithoutGuessing(unittest.TestCase):
    """Khong doc duoc tep: chan va noi su that, KHONG doan la 'da thay doi'."""

    def test_tep_khong_doc_duoc_thi_noi_khong_kiem_tra_duoc(self):
        env, rec = _load_lifecycle(
            attachments=[_att("F1", "to-trinh.pdf", _PDF_A, read_error=True)],
            pkg_files=[_pkg_row()])
        with self.assertRaises(_Throw) as ctx:
            env["on_request_reopened"]("AR-1")
        msg = str(ctx.exception)
        self.assertIn("Không đọc được", msg)
        self.assertNotIn("đã thay đổi so với bộ đã ký", msg,
                         "tep hong tren dia KHONG phai la 'tai lieu da thay doi' - noi sai "
                         "se dan nguoi dung di lam lai phieu trong khi loi la o he thong")
        self.assertEqual(rec["writes"], [])

    def test_goi_thieu_ma_bam_la_su_co_khong_phai_da_doi(self):
        env, _rec = _load_lifecycle(
            attachments=[_att("F1", "to-trinh.pdf", _PDF_A)],
            pkg_files=[_pkg_row(sha=None)])                       # dong tep mat sha256
        with self.assertRaises(_Throw) as ctx:
            env["on_request_reopened"]("AR-1")
        self.assertIn("Không đọc được", str(ctx.exception))


class TestVerdictHelpers(unittest.TestCase):
    def test_ba_ket_qua_khong_phai_hai(self):
        env, _rec = _load_lifecycle(
            attachments=[_att("F1", "to-trinh.pdf", _PDF_A)], pkg_files=[_pkg_row()])
        pkg = _D({"name": "PKG-1", "business_doctype": "EC Payment Request",
                  "business_name": "EC-PAYR-2026-00001"})
        self.assertEqual(env["_signable_content_verdict"](pkg), "unchanged")

    def test_has_collected_signatures_theo_dem(self):
        env, _rec = _load_lifecycle(attachments=[], pkg_files=[], signed_count=2)
        self.assertTrue(env["has_collected_signatures"]("PKG-1"))
        env2, _rec2 = _load_lifecycle(attachments=[], pkg_files=[], signed_count=0)
        self.assertFalse(env2["has_collected_signatures"]("PKG-1"))

    def test_reopen_notice_im_lang_khi_khong_revised(self):
        env, _rec = _load_lifecycle(attachments=[], pkg_files=[])
        self.assertEqual(env["reopen_notice"]({"revised": False}), "")


if __name__ == "__main__":
    unittest.main()
