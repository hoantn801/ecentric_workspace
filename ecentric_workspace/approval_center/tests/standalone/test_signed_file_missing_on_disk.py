# Copyright (c) 2026, eCentric and contributors
"""File ky da luu nhung MAT TREN DIA (08/09, EC-PAYR-2026-00046).

Ban ghi File SIGNED-...DNTT.pdf con, file tren dia khong con -> "Mo file" 404, va
document_setup_state nem FileNotFoundError khi bam SHA tep dai dien -> ca khoi "Tai lieu & ky
so" chet cho MOI tep. Hai viec:
  1. document_setup._rep_sha_or_none: tep mat -> None, log, dong do mang file_missing=True,
     cac dong khac van hien. (AST + exec ham that.)
  2. signed_files.restore_missing_signed_files: tai lai tu SCTS, SHA phai KHOP signed_file_sha256
     da luu moi ghi (ghi dung duong dan cu, khong tao ban ghi moi); lech -> skipped + su kien
     SignedFileRestoreRefused; dry_run khong ghi gi; provider loi -> skipped.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class _PErr(Exception):
    def __init__(self, code, msg="", retryable=False):
        super().__init__(msg); self.code = code; self.retryable = retryable


def _load_signed_files(tmpdir, dsf_rows, provider, sha_stored="abc"):
    """exec signed_files.py voi frappe gia. dsf_rows: list dict(name, file_name, signed_file,
    signed_file_sha256, scts_document_file_id). File doc gia: get_full_path -> tmpdir/<file>.pdf"""
    events = []
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user="admin")
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: "tb"
    fk.utils = types.SimpleNamespace(now_datetime=lambda: None)

    class FileDoc:
        def __init__(self, name):
            self.name = name; self.file_url = "/private/files/%s.pdf" % name
        def get_full_path(self):
            return os.path.join(tmpdir, self.name + ".pdf")

    def get_doc(dt, name=None):
        if dt == "File":
            return FileDoc(name)
        if dt == "EC Digital Signature Package":
            return types.SimpleNamespace(name=name, provider="scts", environment="prod", scts_document_id="DOC-1")
        raise AssertionError(dt)
    fk.get_doc = get_doc
    fk.get_all = lambda dt, filters=None, fields=None, **k: [types.SimpleNamespace(**r) for r in dsf_rows]
    fk.db = types.SimpleNamespace(
        exists=lambda dt, name: True,
        get_value=lambda dt, name, fields=None, as_dict=False, **k: types.SimpleNamespace(
            **{k2: v for k2, v in next(r for r in dsf_rows if r["name"] == name).items()}) if dt == "EC Digital Signature File"
            else {"provider": "scts"},
        set_value=lambda *a, **k: None, sql=lambda *a, **k: [], count=lambda *a, **k: 0)
    ev = types.ModuleType("ecentric_workspace.platform.esign.events")
    ev.emit = lambda et, **k: events.append((et, k.get("request_meta")))
    prov = types.ModuleType("ecentric_workspace.platform.esign.providers")
    prov.get_adapter = lambda s: provider
    base = types.ModuleType("ecentric_workspace.platform.esign.providers.base")
    base.ProviderError = _PErr
    san = types.ModuleType("ecentric_workspace.platform.esign.sanitize"); san.safe_error = lambda e: str(e)
    st = types.ModuleType("ecentric_workspace.platform.esign.state"); st.DSR_TERMINAL = ()
    fu = types.ModuleType("frappe.utils"); fu.now_datetime = lambda: None
    mods = {"frappe": fk, "frappe.utils": fu, "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.providers": prov,
            "ecentric_workspace.platform.esign.providers.base": base,
            "ecentric_workspace.platform.esign.sanitize": san,
            "ecentric_workspace.platform.esign.state": st}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_signed_files_under_test")
        exec(compile(_read("platform", "esign", "signed_files.py"), "signed_files.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._events = events
    return m


class TestRestore(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.rows = [{"name": "DSF-1", "file_name": "a.pdf", "signed_file": "F1", "signed_file_sha256": "sha-ok",
                      "scts_document_file_id": "FID-1"},
                     {"name": "DSF-2", "file_name": "b.pdf", "signed_file": "F2", "signed_file_sha256": "sha-b",
                      "scts_document_file_id": "FID-2"}]
        with open(os.path.join(self.tmp, "F2.pdf"), "wb") as fh:
            fh.write(b"%PDF-b")                       # F2 con tren dia; F1 mat

    def _provider(self, sha="sha-ok", fail=False):
        calls = []

        def get_signed_document(doc_id, file_id):
            calls.append((doc_id, file_id))
            if fail:
                raise _PErr("provider_down", "x", retryable=True)
            return {"content": b"%PDF-restored", "sha256": sha, "size": 13}
        p = types.SimpleNamespace(get_signed_document=get_signed_document, calls=calls)
        return p

    def test_chi_bao_tep_mat(self):
        m = _load_signed_files(self.tmp, self.rows, self._provider())
        miss = m.missing_signed_files("PKG-1")
        self.assertEqual([x["dsf"] for x in miss], ["DSF-1"])
        self.assertEqual(miss[0]["reason"], "missing_on_disk")

    def test_dry_run_khong_ghi(self):
        p = self._provider()
        m = _load_signed_files(self.tmp, self.rows, p)
        rep = m.restore_missing_signed_files("PKG-1", dry_run=True)
        self.assertEqual([x["dsf"] for x in rep["missing"]], ["DSF-1"])
        self.assertEqual(rep["restored"], []); self.assertEqual(p.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "F1.pdf")))

    def test_phuc_hoi_dung_duong_dan_cu_khi_sha_khop(self):
        p = self._provider(sha="sha-ok")
        m = _load_signed_files(self.tmp, self.rows, p)
        rep = m.restore_missing_signed_files("PKG-1", dry_run=False)
        self.assertEqual([x["dsf"] for x in rep["restored"]], ["DSF-1"])
        self.assertEqual(p.calls, [("DOC-1", "FID-1")])            # chi tai tep mat, khong tai F2
        with open(os.path.join(self.tmp, "F1.pdf"), "rb") as fh:
            self.assertEqual(fh.read(), b"%PDF-restored")
        with open(os.path.join(self.tmp, "F2.pdf"), "rb") as fh:
            self.assertEqual(fh.read(), b"%PDF-b")                    # F2 khong bi dong
        self.assertIn("SignedFileRestored", [e for e, _ in m._events])
        self.assertEqual(m.missing_signed_files("PKG-1"), [])

    def test_sha_lech_thi_tu_choi_khong_ghi(self):
        p = self._provider(sha="sha-KHAC")
        m = _load_signed_files(self.tmp, self.rows, p)
        rep = m.restore_missing_signed_files("PKG-1", dry_run=False)
        self.assertEqual(rep["restored"], [])
        self.assertEqual(rep["skipped"][0]["reason"], "sha_mismatch")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "F1.pdf")))
        self.assertIn("SignedFileRestoreRefused", [e for e, _ in m._events])

    def test_provider_loi_thi_skipped(self):
        m = _load_signed_files(self.tmp, self.rows, self._provider(fail=True))
        rep = m.restore_missing_signed_files("PKG-1", dry_run=False)
        self.assertEqual(rep["restored"], []); self.assertIn("provider", rep["skipped"][0]["reason"])


class TestSetupStateSurvives(unittest.TestCase):
    def test_rep_sha_or_none_va_file_missing(self):
        src = _read("platform", "esign", "document_setup.py")
        self.assertIn("def _rep_sha_or_none(rep)", src)
        i = src.index("def get_document_setup_state(")
        body = src[i:]
        self.assertIn("sha = _rep_sha_or_none(rep)", body)
        self.assertNotIn("_dsf_by_sha(pkg_for_dsf, _rep_sha(rep))", body, "duong cu van nem FileNotFoundError")
        self.assertIn('"file_missing": file_missing', body)
        # ham that: tep mat -> None, khong nem
        fk = types.ModuleType("frappe"); fk.log_error = lambda *a, **k: None
        g = {"frappe": fk, "hashing": types.SimpleNamespace(sha256_bytes=lambda b: "h"),
             "pkgsvc": types.SimpleNamespace(raw_file_bytes=lambda n: (_ for _ in ()).throw(FileNotFoundError("gone")))}
        j = src.index("def _rep_sha(rep)"); k = src.index("def _dsf_by_sha(")
        exec(compile(src[j:k], "ds.py", "exec"), g)
        self.assertIsNone(g["_rep_sha_or_none"]({"name": "F", "file_url": "/x"}))
        g["pkgsvc"] = types.SimpleNamespace(raw_file_bytes=lambda n: b"%PDF")
        self.assertEqual(g["_rep_sha_or_none"]({"name": "F"}), "h")
        ui = _read("platform", "esign", "ui", "document_signing_section.html")
        self.assertIn("d.file_missing", ui)
        api = _read("platform", "esign", "api.py")
        self.assertIn("def restore_missing_signed_files(payment_request_name, dry_run=1)", api)
        self.assertIn("perms.assert_system_manager()", api[api.index("def restore_missing_signed_files("):][:400])


if __name__ == "__main__":
    unittest.main()
