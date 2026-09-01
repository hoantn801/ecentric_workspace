# Copyright (c) 2026, eCentric and contributors
"""E2E vong doi: ky xong -> tai PDF da ky -> sha lech -> ngung thu / mo lai (signed_files).

Nhung dieu giu, tren HAM THAT:

  1. Goi KHONG co scts_document_id: khong lam gi, khong dung adapter, khong phat su kien
     loi nao - "chua co tai lieu ben provider" khong phai la mot su co.
  2. Con chan ky dang bay (cap N+1 chua xong): KHONG tai - mot ban PDF tai som la ban
     THIEU chu ky; va khong duoc goi mang khi chua qua cong nay.
  3. Tai lieu 0 nguoi ky ma trang thai "hoan tat": KHONG tin (lop loi UAT VOID 5).
  4. SHA ban tai ve KHAC ban da chap nhan: GIU NGUYEN ban da chap nhan, luu mot ban
     REVIEW-<sha8>-<ten> de doi chieu, ha co signed_bundle_complete, mo dung MOT nhac
     viec (dedupe) - khong bao gio ghi de.
  5. abandon/resume: bat buoc ly do, chan khi goi da du PDF, idempotent, mo lai duoc.
  6. [BUG TAI HIEN - test do o cuoi] signed_files.py:171 va :210 import
     `ecentric_workspace.platform.esign.perms` - module nay KHONG TON TAI (ten that la
     `permissions`). Moi cu bam "Ngung thu lai"/"Mo lai" chet bang ModuleNotFoundError,
     tuc vong lap tai lai vo han KHONG THE dung tu giao dien. Bo test cu khong thay vi
     no grep chuoi 'assert_system_manager' trong nguon thay vi GOI ham.
     Cac test logic o tren tiem san mot module `perms` gia de qua duoc cho import hong
     va kiem phan logic phia sau; rieng test do thi KHONG tiem - no do dung tai cho hong.
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


class _ValidationError(_Throw):
    pass


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


def _event_types_declared():
    j = json.loads(_read("approval_center", "doctype", "ec_digital_signature_event",
                         "ec_digital_signature_event.json"))
    for f in j["fields"]:
        if f.get("fieldname") == "event_type":
            return set((f.get("options") or "").split("\n"))
    raise AssertionError("khong tim thay truong event_type")


_EVENT_TYPES = _event_types_declared()


class _FakeDB(object):
    def __init__(self, tables, list_rows=None):
        self.tables = tables
        self.list_rows = list_rows or {}
        self.writes = []

    def _check(self, dt, fields):
        known = _FIELDS.get(dt)
        if known is None:
            return
        fl = [fields] if isinstance(fields, str) else list(fields or [])
        for f in fl:
            if f == "*":
                continue
            assert f in known, "truong %r khong co tren DocType %s" % (f, dt)

    def _match(self, row, filters):
        for k, v in (filters or {}).items():
            if isinstance(v, list):
                op = v[0]
                if op == "in" and row.get(k) not in v[1]:
                    return False
                if op == "!=" and row.get(k) == v[1]:
                    return False
                if op == "not in" and row.get(k) in v[1]:
                    return False
                if op == "is":
                    have = bool(row.get(k))
                    if v[1] == "set" and not have:
                        return False
                    if v[1] == "not set" and have:
                        return False
            elif row.get(k) != v:
                return False
        return True

    def get_value(self, dt, name_or_filters, fields=None, as_dict=False, for_update=False,
                  order_by=None, **kw):
        self._check(dt, fields)
        if isinstance(name_or_filters, dict):
            row = None
            for n, r in self.tables.get(dt, {}).items():
                if self._match(r, name_or_filters):
                    row = dict(r, name=n)
                    break
        else:
            r = self.tables.get(dt, {}).get(name_or_filters)
            row = dict(r, name=name_or_filters) if r is not None else None
        if row is None:
            return None
        if fields == "*":
            return _D(row) if as_dict else row
        if isinstance(fields, str) or fields is None:
            return row.get(fields or "name")
        out = {x: row.get(x) for x in fields}
        return _D(out) if as_dict else tuple(out.values())

    def set_value(self, dt, name, field, value=None):
        self.writes.append((dt, name, field, value))
        row = self.tables.setdefault(dt, {}).setdefault(name, {})
        if isinstance(field, dict):
            row.update(field)
        else:
            row[field] = value

    def exists(self, dt, filters):
        if isinstance(filters, str):
            return filters if filters in self.tables.get(dt, {}) else None
        for n, r in self.tables.get(dt, {}).items():
            if self._match(r, filters):
                return n
        return None

    def count(self, dt, filters=None):
        return len([1 for _n, r in self.tables.get(dt, {}).items()
                    if self._match(r, filters)])


class _Adapter(object):
    def __init__(self, doc_state=None, signed_result=None):
        self.doc_state = doc_state
        self.signed_result = signed_result
        self.poll_calls = []
        self.get_calls = []

    def poll_status(self, doc_id):
        self.poll_calls.append(doc_id)
        return self.doc_state

    def get_signed_document(self, doc_id, file_id):
        self.get_calls.append((doc_id, file_id))
        return self.signed_result


def _load_sf(tables, dsr_rows=(), adapter=None, perms_stub=True):
    """Exec signed_files.py that. dsr_rows phuc vu get_all tren DSR; adapter la provider gia."""
    import sys

    rec = {"events": [], "inserts": [], "logs": [], "adapter_factory_calls": 0}
    db = _FakeDB(tables)

    def get_all(dt, filters=None, fields=None, limit_page_length=None, order_by=None,
                pluck=None, **kw):
        if dt == "EC Digital Signature Request":
            return [_D(r) for r in dsr_rows if db._match(r, filters)]
        if dt == "EC Digital Signature File":
            out = []
            for n, r in tables.get(dt, {}).items():
                if db._match(r, filters):
                    out.append(_D(dict(r, name=n)))
            return out
        return []

    seq = {"n": 0}

    def get_doc(d, name=None):
        if isinstance(d, dict):
            rec["inserts"].append(dict(d))
            seq["n"] += 1
            made = "NEW-%d" % seq["n"]

            class _Ins(object):
                def insert(self, **kw):
                    return types.SimpleNamespace(name=made)
            return _Ins()
        raise AssertionError("get_doc(%r) khong mong doi" % d)

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = db
    frappe_mod.get_all = get_all
    frappe_mod.get_doc = get_doc
    frappe_mod._ = lambda s: s
    frappe_mod._dict = _D
    frappe_mod.session = types.SimpleNamespace(user="admin.sm@ec.vn")
    frappe_mod.ValidationError = _ValidationError
    frappe_mod.log_error = lambda *a, **kw: rec["logs"].append(("error_log", a))
    frappe_mod.get_traceback = lambda: "tb"

    def _throw(msg, exc=None):
        raise (exc or _Throw)(msg)

    frappe_mod.throw = _throw

    utils_mod = types.ModuleType("frappe.utils")
    utils_mod.now_datetime = lambda: "2026-09-01 12:00:00"
    frappe_mod.utils = utils_mod

    state_mod = types.ModuleType("state")
    exec(compile(_read("platform", "esign", "state.py"), "state.py", "exec"),
         state_mod.__dict__)

    events_mod = types.ModuleType("events")

    def emit(event_type, **kwargs):
        assert event_type in _EVENT_TYPES, \
            "su kien %r chua khai bao trong DocType Event" % event_type
        rec["events"].append((event_type, kwargs))

    events_mod.emit = emit

    base_mod = types.ModuleType("providers.base")

    class ProviderError(Exception):
        def __init__(self, code, msg, retryable=False):
            super(ProviderError, self).__init__(msg)
            self.code, self.retryable = code, retryable

    base_mod.ProviderError = ProviderError

    providers_mod = types.ModuleType("providers")

    def get_adapter(settings):
        rec["adapter_factory_calls"] += 1
        return adapter

    providers_mod.get_adapter = get_adapter
    providers_mod.base = base_mod

    sanitize_mod = types.ModuleType("sanitize")
    sanitize_mod.safe_error = lambda e: str(e)[:200]

    perms_mod = types.ModuleType("permissions")
    perms_mod.assert_system_manager = lambda: rec["logs"].append(("sm_check",))

    engine_mod = types.ModuleType("transitions")
    engine_mod.log_action = lambda *a, **kw: rec["logs"].append(("log_action", a, kw))
    wf_pkg = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    wf_pkg.transitions = engine_mod

    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.state = state_mod
    esign_pkg.events = events_mod
    esign_pkg.sanitize = sanitize_mod
    esign_pkg.providers = providers_mod
    esign_pkg.permissions = perms_mod
    if perms_stub:
        # cho import hong (signed_files goi `import perms`) qua duoc, DE kiem logic sau no.
        # Test BUG o duoi nap voi perms_stub=False.
        esign_pkg.perms = perms_mod

    mods = {
        "frappe": frappe_mod,
        "frappe.utils": utils_mod,
        "ecentric_workspace.platform.esign": esign_pkg,
        "ecentric_workspace.platform.esign.state": state_mod,
        "ecentric_workspace.platform.esign.events": events_mod,
        "ecentric_workspace.platform.esign.sanitize": sanitize_mod,
        "ecentric_workspace.platform.esign.providers": providers_mod,
        "ecentric_workspace.platform.esign.providers.base": base_mod,
        "ecentric_workspace.platform.esign.permissions": perms_mod,
        "ecentric_workspace.approval_center.shared.workflow": wf_pkg,
        "ecentric_workspace.approval_center.shared.workflow.transitions": engine_mod,
    }
    if perms_stub:
        mods["ecentric_workspace.platform.esign.perms"] = perms_mod
    saved = {k: sys.modules.get(k) for k in mods}
    for k, v in mods.items():
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("platform", "esign", "signed_files.py"), "signed_files.py",
                     "exec"), env)
        return env, db, rec, (saved, sys)
    except Exception:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        raise


class _Ctx(object):
    def __init__(self, *a, **kw):
        self._a, self._kw = a, kw

    def __enter__(self):
        self.env, self.db, self.rec, (self._saved, self._sys) = _load_sf(*self._a, **self._kw)
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                self._sys.modules.pop(k, None)
            else:
                self._sys.modules[k] = v
        return False


def _pkg_tables(scts_id="SCTS-DOC-1", bundle_complete=0, abandoned=0):
    return {"EC Digital Signature Package": {
        "PKG-1": {"provider": "SCTS", "environment": "UAT",
                  "scts_document_id": scts_id,
                  "business_doctype": "EC Payment Request",
                  "business_name": "EC-PAYR-2026-00001", "status": "Active",
                  "approval_request": "AR-1",
                  "signed_bundle_complete": bundle_complete,
                  "retrieval_abandoned": abandoned}},
        "EC Digital Signature Provider Settings": {
        "SET-1": {"provider": "SCTS", "environment": "UAT", "integration_enabled": 1}}}


class TestNoProviderDocumentIsNotAnIncident(unittest.TestCase):
    def test_khong_co_scts_document_id_thi_khong_lam_gi(self):
        with _Ctx(_pkg_tables(scts_id=None), adapter=_Adapter()) as c:
            out = c.env["retrieve_and_store_for_package"]("PKG-1")
            self.assertEqual(out, {"ok": False, "reason": "no_provider_document"})
            self.assertEqual(c.rec["adapter_factory_calls"], 0,
                             "chua co tai lieu ben provider thi khong duoc dung toi mang")
            self.assertEqual(c.rec["events"], [], "day la CHO, khong phai su co")


class TestPartialSigningNeverDownloads(unittest.TestCase):
    def _pkg(self, c):
        return c.db.get_value("EC Digital Signature Package", "PKG-1", "*", as_dict=True)

    def test_con_chan_ky_dang_bay_thi_chan_va_khong_goi_mang(self):
        adapter = _Adapter()
        rows = [{"name": "DSR-1", "status": "Approval Completed", "package": "PKG-1"},
                {"name": "DSR-2", "status": "Verifying", "package": "PKG-1"}]
        with _Ctx(_pkg_tables(), dsr_rows=rows, adapter=adapter) as c:
            ok, reason = c.env["_terminal_signed_ok"](adapter, self._pkg(c))
            self.assertFalse(ok)
            self.assertIn("signing_still_in_flight", reason)
            self.assertIn("Verifying", reason)
            self.assertEqual(adapter.poll_calls, [],
                             "chua du dieu kien noi bo thi khong duoc hoi provider")

    def test_khong_co_nguoi_ky_nao_thi_khong_tin_hoan_tat(self):
        doc = types.SimpleNamespace(status="Signed", signers=[])
        adapter = _Adapter(doc_state=doc)
        rows = [{"name": "DSR-1", "status": "Approval Completed", "package": "PKG-1"}]
        with _Ctx(_pkg_tables(), dsr_rows=rows, adapter=adapter) as c:
            ok, reason = c.env["_terminal_signed_ok"](adapter, self._pkg(c))
            self.assertFalse(ok)
            self.assertEqual(reason, "no_signers_on_document",
                             "0 nguoi ky + status 'hoan tat' chinh la lop loi UAT VOID 5")

    def test_mot_nguoi_con_pending_thi_van_chan_du_status_noi_xong(self):
        doc = types.SimpleNamespace(status="Signed", signers=[
            {"status": "signed", "user_id": "u1", "email": "a@ec.vn"},
            {"status": "pending", "user_id": "u2", "email": "b@ec.vn"}])
        adapter = _Adapter(doc_state=doc)
        rows = [{"name": "DSR-1", "status": "Approval Completed", "package": "PKG-1"}]
        with _Ctx(_pkg_tables(), dsr_rows=rows, adapter=adapter) as c:
            ok, reason = c.env["_terminal_signed_ok"](adapter, self._pkg(c))
            self.assertFalse(ok)
            self.assertIn("non_signed_signer_present", reason)

    def test_du_het_thi_moi_dat(self):
        """Chan ky phai co DANH TINH thi moi doi chieu duoc.

        Tu 01/09, `status` terminal khong con la duong tat bo qua doi chieu danh tinh, nen
        ban gia phai khai `action="Sign"` + nguoi ky nhu that. Ban gia thieu hai truong do
        se bi tu choi voi "no_expected_signers" - dung, va do la fail-closed.
        """
        doc = types.SimpleNamespace(status="Signed", signers=[
            {"status": "signed", "user_id": "u1", "email": "a@ec.vn"}])
        adapter = _Adapter(doc_state=doc)
        rows = [{"name": "DSR-1", "status": "Approval Completed", "package": "PKG-1",
                 "action": "Sign", "effective_scts_user_id": "u1",
                 "actor_user": "a@ec.vn", "approver": "a@ec.vn"}]
        with _Ctx(_pkg_tables(), dsr_rows=rows, adapter=adapter) as c:
            ok, reason = c.env["_terminal_signed_ok"](adapter, self._pkg(c))
            self.assertTrue(ok)
            self.assertEqual(reason, "terminal_and_all_expected_signers_signed")

    def test_KHONG_co_danh_tinh_ky_vong_thi_tu_choi(self):
        """Fail-closed: khong biet ai duoc ky thi khong the ket luan la da ky dung."""
        doc = types.SimpleNamespace(status="Signed", signers=[
            {"status": "signed", "user_id": "u1", "email": "a@ec.vn"}])
        adapter = _Adapter(doc_state=doc)
        rows = [{"name": "DSR-1", "status": "Approval Completed", "package": "PKG-1"}]
        with _Ctx(_pkg_tables(), dsr_rows=rows, adapter=adapter) as c:
            ok, reason = c.env["_terminal_signed_ok"](adapter, self._pkg(c))
            self.assertFalse(ok)
            self.assertEqual(reason, "no_expected_signers")


class TestHashMismatchKeepsAcceptedFile(unittest.TestCase):
    _SHA_OLD = "a" * 64
    _SHA_NEW = "b" * 64

    def _tables(self):
        t = _pkg_tables()
        t["EC Digital Signature File"] = {
            "DSF-1": {"package": "PKG-1", "file": "F-copy", "file_name": "to-trinh.pdf",
                      "requires_signature": 1, "scts_document_file_id": "FID-1",
                      "signed_file": "FILE-ACCEPTED", "signed_file_sha256": self._SHA_OLD}}
        return t

    def _dsf(self, c):
        return c.db.get_value("EC Digital Signature File", "DSF-1",
                              ["name", "file", "file_name", "scts_document_file_id",
                               "signed_file", "signed_file_sha256"], as_dict=True)

    def test_cung_sha_thi_bo_qua_khong_goi_mang(self):
        adapter = _Adapter()
        with _Ctx(self._tables(), adapter=adapter) as c:
            pkg = c.db.get_value("EC Digital Signature Package", "PKG-1", "*", as_dict=True)
            out = c.env["_retrieve_one"](pkg, adapter, self._dsf(c))
            self.assertTrue(out["duplicate"])
            self.assertEqual(adapter.get_calls, [])
            self.assertEqual([e[0] for e in c.rec["events"]], ["SignedFileDuplicateSkipped"])

    def test_sha_khac_giu_ban_cu_luu_review_va_ha_co_bundle(self):
        adapter = _Adapter(signed_result={"sha256": self._SHA_NEW,
                                          "content": b"%PDF khac", "size": 9})
        with _Ctx(self._tables(), adapter=adapter) as c:
            pkg = c.db.get_value("EC Digital Signature Package", "PKG-1", "*", as_dict=True)
            out = c.env["_retrieve_one"](pkg, adapter, self._dsf(c), force=True)
            self.assertTrue(out["hash_mismatch"])
            # 1. ban da chap nhan KHONG bi dong toi
            row = c.db.tables["EC Digital Signature File"]["DSF-1"]
            self.assertEqual(row["signed_file"], "FILE-ACCEPTED",
                             "khong bao gio ghi de ban PDF da ky da chap nhan")
            self.assertEqual(row["signed_file_sha256"], self._SHA_OLD)
            # 2. ban ung vien duoc luu voi ten REVIEW-<sha8>-<ten>
            names = [i.get("file_name") for i in c.rec["inserts"] if i.get("doctype") == "File"]
            self.assertIn("REVIEW-%s-to-trinh.pdf" % self._SHA_NEW[:8], names)
            # 3. co bundle bi ha de khong ai tuong da xong
            self.assertEqual(
                c.db.tables["EC Digital Signature Package"]["PKG-1"]["signed_bundle_complete"], 0)
            # 4. su kien + nhac viec
            self.assertIn("SignedFileHashMismatch", [e[0] for e in c.rec["events"]])
            todos = [i for i in c.rec["inserts"] if i.get("doctype") == "ToDo"]
            self.assertEqual(len(todos), 1)

    def test_nhac_viec_review_khong_nhan_doi(self):
        adapter = _Adapter(signed_result={"sha256": self._SHA_NEW,
                                          "content": b"%PDF khac", "size": 9})
        t = self._tables()
        t["ToDo"] = {"TODO-1": {"reference_type": "EC Digital Signature Package",
                                "reference_name": "PKG-1", "status": "Open",
                                "description": "[EC-ESIGN-SIGNED-FILE-REVIEW] cu"}}
        # ban REVIEW cung ton tai san -> khong luu ban thu hai
        t["File"] = {"FILE-REV": {"attached_to_doctype": "EC Payment Request",
                                  "attached_to_name": "EC-PAYR-2026-00001",
                                  "file_name": "REVIEW-%s-to-trinh.pdf" % self._SHA_NEW[:8]}}
        with _Ctx(t, adapter=adapter) as c:
            pkg = c.db.get_value("EC Digital Signature Package", "PKG-1", "*", as_dict=True)
            out = c.env["_retrieve_one"](pkg, adapter, self._dsf(c), force=True)
            self.assertTrue(out["hash_mismatch"])
            self.assertEqual(c.rec["inserts"], [],
                             "REVIEW da co + ToDo da mo -> khong duoc nhan doi thu gi")


class TestAbandonAndResume(unittest.TestCase):
    def test_bat_buoc_ly_do(self):
        with _Ctx(_pkg_tables()) as c:
            with self.assertRaises(_ValidationError):
                c.env["abandon_retrieval"]("PKG-1", "  ")
            self.assertEqual(c.db.writes, [])

    def test_goi_da_du_pdf_thi_khong_co_gi_de_ngung(self):
        with _Ctx(_pkg_tables(bundle_complete=1)) as c:
            with self.assertRaises(_Throw) as ctx:
                c.env["abandon_retrieval"]("PKG-1", "tai lieu 404")
            self.assertIn("đã lấy đủ", str(ctx.exception))

    def test_ngung_ghi_du_vet_va_idempotent(self):
        with _Ctx(_pkg_tables()) as c:
            out = c.env["abandon_retrieval"]("PKG-1", "tai lieu 404 ben SCTS tu 23/08")
            self.assertEqual(out, {"ok": True})
            row = c.db.tables["EC Digital Signature Package"]["PKG-1"]
            self.assertEqual(row["retrieval_abandoned"], 1)
            self.assertEqual(row["retrieval_abandoned_by"], "admin.sm@ec.vn")
            self.assertIn("404", row["retrieval_abandoned_reason"])
            self.assertIn("SignedRetrievalAbandoned", [e[0] for e in c.rec["events"]])
            self.assertTrue(any(x[0] == "log_action" for x in c.rec["logs"]),
                            "quyet dinh ngung phai nam trong lich su phieu")
            n = len(c.db.writes)
            out2 = c.env["abandon_retrieval"]("PKG-1", "tai lieu 404 ben SCTS tu 23/08")
            self.assertEqual(out2, {"ok": True, "already": True})
            self.assertEqual(len(c.db.writes), n, "lan hai khong ghi them gi")

    def test_mo_lai_duoc(self):
        with _Ctx(_pkg_tables(abandoned=1)) as c:
            out = c.env["resume_retrieval"]("PKG-1")
            self.assertEqual(out, {"ok": True})
            self.assertEqual(
                c.db.tables["EC Digital Signature Package"]["PKG-1"]["retrieval_abandoned"], 0)
            self.assertIn("SignedRetrievalResumed", [e[0] for e in c.rec["events"]])


class TestBugPermsImportDoesNotExist(unittest.TestCase):
    """[BUG TAI HIEN] Nut 'Ngung thu lai' chet ngay khi bam.

    signed_files.py:171 (va :210) viet `from ecentric_workspace.platform.esign import
    perms` - nhung module do ten la `permissions`; `perms.py` khong ton tai tren dia
    (kiem chung: ls platform/esign/). Moi loi goi abandon_retrieval / resume_retrieval
    no ModuleNotFoundError truoc ca dong kiem quyen.

    Test nay nap signed_files trong moi truong CO `permissions` (ten dung) nhung KHONG
    co `perms` (ten sai) - dung nhu tren server that. Code dung thi test xanh; code hien
    tai thi do, va do la bao cao loi.
    """

    def test_BUG_ngung_thu_lai_phai_chay_duoc_chu_khong_chet_o_import(self):
        with _Ctx(_pkg_tables(), perms_stub=False) as c:
            try:
                out = c.env["abandon_retrieval"]("PKG-1", "tai lieu 404 ben SCTS")
            except ImportError as e:
                self.fail(
                    "BUG signed_files.py:171 - 'from ecentric_workspace.platform.esign "
                    "import perms' nhung module ten that la 'permissions'; nut Ngung thu "
                    "lai/Mo lai chet ngay khi bam, vong lap tai 404 vo han KHONG dung "
                    "duoc tu giao dien. Loi goc: %s" % e)
            self.assertEqual(out, {"ok": True})


if __name__ == "__main__":
    unittest.main()
