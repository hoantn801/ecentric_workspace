# Copyright (c) 2026, eCentric and contributors
"""BOT 1 - vong 3: TINH TOAN VEN cua PDF da ky giua SCTS va ban ERP giu.

Cau hoi cot loi cua Hoan: mot PDF ma SCTS tra ve co the LECH so voi cai ERP thuc su
cho ky (thay noi dung, them trang, nguoi ky la, thieu nguoi ky ky vong) - va he thong
CO phat hien duoc khong, hay co bao gio ERP tin nham mot PDF khac va dong dau "da ky".

Bo test nay KHONG grep chu thich. No CAT lat ma nguon that cua signed_files.py roi CHAY
`_terminal_signed_ok`, `_retrieve_one`, `_store_hash_mismatch` voi mot `frappe` gia va mot
adapter gia - dung mo hinh cua test_esign_ops_inbox / test_retrieval_rounds. Moi khang dinh
deu duoc chung minh bang DOT BIEN: doi mot dieu kien dau vao thi ket qua doi theo.

Phat hien nang nhat (V3-BOT1-01, do): `_terminal_signed_ok` co loi tat
`if status in _TERMINAL_SIGNED: return True` chay TRUOC khoi doi chieu danh tinh nguoi ky.
Khi nha cung cap bao trang thai cap tai lieu la "completed" thi khoi kiem "dung nguoi ky
ky vong" (dong 106-126) tro thanh MA CHET - danh tinh nguoi ky khong con duoc doi chieu
tren duong di chinh. Dung lop loi UAT VOID 5: bao "da ky" khi nguoi ky khong phai nguoi
ky ky vong.
"""
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))

DSR = "EC Digital Signature Request"
DSF = "EC Digital Signature File"
PKG = "EC Digital Signature Package"

DSR_TERMINAL = ("Approval Completed", "Permanent Failure", "Cancelled", "Rejected",
                "Superseded")


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


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _FakeEvents(object):
    def __init__(self):
        self.emitted = []

    def emit(self, event_type, **kw):
        self.emitted.append((event_type, kw))

    def types(self):
        return [e[0] for e in self.emitted]


class _FakeDoc(object):
    """Giong doc Frappe: .insert() tra ve chinh no, .name suy tu file_name."""

    def __init__(self, d):
        self._d = d
        self.name = d.get("file_name") or "NEW-FILE"

    def insert(self, **kw):
        return self


class _FakeDB(object):
    def __init__(self, dsf_row):
        self.dsf = dict(dsf_row)          # trang thai DONG TEP hien tai (reload duoi khoa)
        self.pkg = {}
        self.set_calls = []               # moi lan ghi -> de doi soat "co ghi de khong"
        self.locked = []                  # moi lan for_update -> chung minh co khoa dong
        self.exists_map = {}              # dt -> gia tri exists tra ve

    def get_value(self, dt, name, fields=None, as_dict=False, for_update=False, **kw):
        if for_update:
            self.locked.append((dt, name))
            return name
        if dt == DSF:
            if fields == "name":
                return name
            if as_dict and isinstance(fields, (list, tuple)):
                return _D({k: self.dsf.get(k) for k in fields})
        return None

    def set_value(self, dt, name, field_or_dict, value=None):
        if isinstance(field_or_dict, dict):
            vals = dict(field_or_dict)
        else:
            vals = {field_or_dict: value}
        self.set_calls.append((dt, name, vals))
        if dt == DSF:
            self.dsf.update(vals)
        elif dt == PKG:
            self.pkg.update(vals)

    def exists(self, dt, filters=None):
        return self.exists_map.get(dt)

    def count(self, *a, **k):
        return 0


class _FakeFrappe(object):
    def __init__(self, db, dsr_legs=(), expected_sign_rows=(), inserted=None):
        self.db = db
        self._dsr_legs = list(dsr_legs)
        self._expected = list(expected_sign_rows)
        self.inserted = inserted if inserted is not None else []
        self.utils = types.SimpleNamespace(now_datetime=lambda: "2026-09-01 00:00:00")

    def get_all(self, dt, filters=None, fields=None, **kw):
        filters = filters or {}
        if dt == DSR and str(filters.get("action")) == "Sign":
            return [_D(r) for r in self._expected]
        if dt == DSR:
            return [_D(r) for r in self._dsr_legs]
        return []

    def get_doc(self, doc):
        d = _FakeDoc(doc)
        self.inserted.append(doc)
        return d


class _FakeAdapter(object):
    def __init__(self, doc=None, signed=None):
        self._doc = doc
        self._signed = signed
        self.poll_calls = 0
        self.get_signed_calls = 0

    def poll_status(self, doc_id):
        self.poll_calls += 1
        return self._doc

    def get_signed_document(self, doc_id, file_id=None):
        self.get_signed_calls += 1
        return self._signed


def _load_signed_files(frappe_obj, events_obj):
    """Cat lat tu `PKG = ...` toi het file va CHAY that voi frappe/events gia.

    Cac ham khong duoc goi (retrieve_and_store, abandon, ...) tham chieu ProviderError /
    get_adapter / safe_error - chi khi CHAY moi can, nen tiem san cho khoi NameError luc exec.
    """
    with io.open(os.path.join(_ROOT, "platform", "esign", "signed_files.py"),
                 encoding="utf-8") as _fh:
        src = _fh.read()
    slice_src = src[src.index('PKG = "EC Digital Signature Package"'):]
    mod = types.ModuleType("sf_slice")
    mod.frappe = frappe_obj
    mod.events = events_obj
    mod.now_datetime = frappe_obj.utils.now_datetime
    mod.DSR_TERMINAL = DSR_TERMINAL

    class _ProviderError(Exception):
        def __init__(self, code="", msg="", retryable=False):
            self.code = code
            self.retryable = retryable

    mod.ProviderError = _ProviderError
    mod.get_adapter = lambda *a, **k: None
    mod.safe_error = lambda e: {"code": getattr(e, "code", "")}
    exec(compile(slice_src, "signed_files.py", "exec"), mod.__dict__)
    return mod


def _doc(status, signers):
    return types.SimpleNamespace(status=status, signers=signers, files=[])


def _signer(status="signed", user_id=None, email=None):
    return {"status": status, "user_id": user_id, "email": email}


# --------------------------------------------------------------------------- #
# V3-BOT1-01 (DO): loi tat trang thai bo qua doi chieu danh tinh nguoi ky
# --------------------------------------------------------------------------- #
class TestTerminalStatusNoLongerBypassesIdentity(unittest.TestCase):
    """`_terminal_signed_ok`: khi status cap tai lieu la 'completed', khoi doi chieu
    'dung nguoi ky ky vong' khong con chay - danh tinh nguoi ky khong duoc xac minh."""

    def _pkg(self):
        return _D({"name": "PKG-1", "scts_document_id": "doc-1"})

    def _env(self, doc, expected_sign_rows):
        ev = _FakeEvents()
        # ca hai chan ky da hoan tat -> qua cong 1 (moi chan da xong, khong con chay)
        legs = [{"name": "DSR-1", "status": "Approval Completed"},
                {"name": "DSR-2", "status": "Approval Completed"}]
        fr = _FakeFrappe(_FakeDB({}), dsr_legs=legs, expected_sign_rows=expected_sign_rows)
        mod = _load_signed_files(fr, ev)
        return mod, _FakeAdapter(doc=doc)

    def test_nguoi_ky_LA_van_qua_cong_khi_status_completed(self):
        """DA VA 01/09: nguoi ky duy nhat la NGUOI NGOAI thi bi chan, KE CA khi tai lieu
        mang status 'completed'. Truoc khi va, loi tat terminal bo qua toan bo khoi doi
        chieu danh tinh - PDF cua nguoi la van duoc tai ve va dong dau da ky."""
        expected = [{"effective_scts_user_id": "U-INTERNAL",
                     "actor_user": "approver@ec.vn", "approver": None}]
        outsider = _doc("completed", [_signer(user_id="OUTSIDER",
                                              email="stranger@evil.com")])
        mod, adapter = self._env(outsider, expected)
        ok, reason = mod._terminal_signed_ok(adapter, self._pkg())
        self.assertFalse(ok, "nguoi ky la KHONG duoc qua cong du tai lieu terminal")
        self.assertTrue(
            any(k in reason for k in ("expected_signer_absent", "unexpected_signer_identity")),
            "phai chan vi danh tinh, ly do: %r" % reason)

    def test_DOT_BIEN_bo_loi_tat_thi_danh_tinh_MOI_chan_duoc(self):
        """Chung minh khoi doi chieu THUC SU biet chan nguoi la - chi la no bi loi tat
        nhay qua. Doi status sang mot gia tri KHONG terminal: cung nguoi ky la do, gio
        ham chay xuong khoi fallback va tra 'unexpected_signer_identity'."""
        expected = [{"effective_scts_user_id": "U-INTERNAL",
                     "actor_user": "approver@ec.vn", "approver": None}]
        outsider = _doc("in_progress", [_signer(user_id="OUTSIDER",
                                               email="stranger@evil.com")])
        mod, adapter = self._env(outsider, expected)
        ok, reason = mod._terminal_signed_ok(adapter, self._pkg())
        self.assertFalse(ok, "khi khong co loi tat status, danh tinh nguoi la phai bi chan")
        self.assertIn("expected_signer_absent", reason)

    def test_thieu_nguoi_ky_ky_vong_van_qua_khi_completed(self):
        """DA VA 01/09: thieu mot nguoi ky vong thi bi chan, ke ca khi status 'completed'.
        Mot chung tu duyet chi thieu chu ky cua mot cap la chung tu chua du hieu luc."""
        expected = [{"effective_scts_user_id": "U-A", "actor_user": "a@ec.vn",
                     "approver": None},
                    {"effective_scts_user_id": "U-B", "actor_user": "b@ec.vn",
                     "approver": None}]
        only_one = _doc("completed", [_signer(user_id="U-A", email="a@ec.vn")])
        mod, adapter = self._env(only_one, expected)
        ok, reason = mod._terminal_signed_ok(adapter, self._pkg())
        self.assertFalse(ok, "thieu nguoi ky ky vong ma van qua cong")
        self.assertIn("expected_signer_absent", reason)


# --------------------------------------------------------------------------- #
# Kich ban c (xanh - guard con hieu luc tren duong khong-terminal / 0 nguoi ky)
# --------------------------------------------------------------------------- #
class TestZeroAndNonSignedAreBlocked(unittest.TestCase):
    def _run(self, doc, expected=()):
        ev = _FakeEvents()
        legs = [{"name": "DSR-1", "status": "Approval Completed"}]
        fr = _FakeFrappe(_FakeDB({}), dsr_legs=legs, expected_sign_rows=list(expected))
        mod = _load_signed_files(fr, ev)
        return mod._terminal_signed_ok(_FakeAdapter(doc=doc),
                                       _D({"name": "PKG-1", "scts_document_id": "d"}))

    def test_0_nguoi_ky_bi_chan(self):
        ok, reason = self._run(_doc("completed", []))
        self.assertFalse(ok)
        self.assertEqual(reason, "no_signers_on_document")

    def test_co_nguoi_chua_ky_bi_chan(self):
        ok, reason = self._run(_doc("completed", [_signer(status="pending",
                                                          user_id="U-A")]))
        self.assertFalse(ok)
        self.assertIn("non_signed_signer_present", reason)

    def test_leg_con_chay_thi_khong_tai(self):
        ev = _FakeEvents()
        legs = [{"name": "DSR-1", "status": "Approval Completed"},
                {"name": "DSR-2", "status": "Verifying"}]
        fr = _FakeFrappe(_FakeDB({}), dsr_legs=legs)
        mod = _load_signed_files(fr, ev)
        ok, reason = mod._terminal_signed_ok(
            _FakeAdapter(doc=_doc("completed", [_signer(user_id="U")])),
            _D({"name": "PKG-1", "scts_document_id": "d"}))
        self.assertFalse(ok, "con chan ky dang chay = con chu ky sap toi = PDF con phan")
        self.assertIn("signing_still_in_flight", reason)


# --------------------------------------------------------------------------- #
# Kich ban a/b (re-fetch): sha khac -> GIU ban goc, mo doi soat, KHONG ghi de
# --------------------------------------------------------------------------- #
class TestReRetrievalNeverOverwrites(unittest.TestCase):
    def _mod(self, db, inserted):
        ev = _FakeEvents()
        fr = _FakeFrappe(db, inserted=inserted)
        return _load_signed_files(fr, ev), ev

    def test_sha_khac_giu_ban_goc_va_mo_review(self):
        """SCTS tra PDF KHAC (bi sua / them trang) o lan tai lai -> danh dau mismatch,
        giu con tro signed_file cu, luu ban ung vien rieng. Khong bao gio de len ban goc."""
        db = _FakeDB({"signed_file": "F-OLD", "signed_file_sha256": "OLDSHA"})
        db.exists_map = {"File": None, "ToDo": True}     # chua co ung vien; ToDo da co
        inserted = []
        mod, ev = self._mod(db, inserted)
        f = _D({"name": "DSF-1", "file_name": "hopdong.pdf", "scts_document_file_id": "sf-1",
                "signed_file": "F-OLD", "signed_file_sha256": "OLDSHA"})
        adapter = _FakeAdapter(signed={"content": b"%PDF-fake-tampered",
                                       "sha256": "NEWSHA", "size": 20})
        res = mod._retrieve_one(_D({"name": "PKG-1", "scts_document_id": "doc-1",
                                    "business_doctype": "EC Payment Request",
                                    "business_name": "PR-1"}), adapter, f, force=True)
        self.assertTrue(res.get("hash_mismatch"), "sha khac phai vao duong mismatch")
        self.assertEqual(db.dsf["signed_file"], "F-OLD",
                         "BAN GOC bi ghi de = mat chung tu da ky - KHONG duoc phep")
        self.assertEqual(db.dsf["provider_status"], "SignedHashMismatch")
        self.assertEqual(db.dsf["signed_review_sha256"], "NEWSHA")
        self.assertIn("SignedFileHashMismatch", ev.types())
        # signed_bundle_complete phai bi ha ve 0 (con no doi soat)
        self.assertIn((PKG, "PKG-1", {"signed_bundle_complete": 0}), db.set_calls)

    def test_DOT_BIEN_sha_bang_thi_KHONG_vao_mismatch(self):
        """Doi mot dieu kien: sha tra ve TRUNG ban da chap nhan -> phai la duplicate,
        khong tao ung vien, khong danh mismatch. Chung minh nhanh mismatch do CHINH sha."""
        db = _FakeDB({"signed_file": "F-OLD", "signed_file_sha256": "SAME"})
        inserted = []
        mod, ev = self._mod(db, inserted)
        f = _D({"name": "DSF-1", "file_name": "hopdong.pdf", "scts_document_file_id": "sf-1",
                "signed_file": "F-OLD", "signed_file_sha256": "SAME"})
        adapter = _FakeAdapter(signed={"content": b"%PDF-x", "sha256": "SAME", "size": 5})
        res = mod._retrieve_one(_D({"name": "PKG-1", "scts_document_id": "doc-1"}),
                                adapter, f, force=True)
        self.assertTrue(res.get("duplicate"))
        self.assertNotIn("SignedFileHashMismatch", ev.types())
        self.assertEqual(inserted, [], "sha trung thi khong duoc tao File nao")


# --------------------------------------------------------------------------- #
# Kich ban e (retry): khong tao File doi, khong doi sha da chap nhan
# --------------------------------------------------------------------------- #
class TestRetryIsIdempotent(unittest.TestCase):
    def test_da_co_signed_file_va_khong_force_thi_KHONG_tai_lai(self):
        db = _FakeDB({"signed_file": "F-OLD", "signed_file_sha256": "OLDSHA"})
        ev = _FakeEvents()
        fr = _FakeFrappe(db)
        mod = _load_signed_files(fr, ev)
        f = _D({"name": "DSF-1", "file_name": "hd.pdf", "scts_document_file_id": "sf-1",
                "signed_file": "F-OLD", "signed_file_sha256": "OLDSHA"})
        adapter = _FakeAdapter(signed={"content": b"x", "sha256": "Z", "size": 1})
        res = mod._retrieve_one(_D({"name": "PKG-1", "scts_document_id": "doc-1"}),
                                adapter, f, force=False)
        self.assertTrue(res.get("duplicate"))
        self.assertEqual(adapter.get_signed_calls, 0,
                         "da co ban da ky + khong force -> khong duoc goi mang tai lai")

    def test_lan_dau_tai_luu_ban_ghi_va_dat_sha(self):
        """Lan dau (chua co signed_file): luu File, dat signed_file_sha256 = sha tra ve.
        LUU Y: khong he doi chieu voi DSF.sha256 (ban CHUA ky ERP gui di) - day la diem
        tin cay-mu vao dau ra SCTS o lan cham dau tien (V3-BOT1-02)."""
        db = _FakeDB({"signed_file": None, "signed_file_sha256": None})
        db.exists_map = {"File": None, "ToDo": None}
        inserted = []
        ev = _FakeEvents()
        fr = _FakeFrappe(db, inserted=inserted)
        mod = _load_signed_files(fr, ev)
        f = _D({"name": "DSF-1", "file_name": "hd.pdf", "scts_document_file_id": "sf-1",
                "signed_file": None, "signed_file_sha256": None,
                "sha256": "UNSIGNED-ERP-HASH"})   # bam ban CHUA ky ERP gui di
        adapter = _FakeAdapter(signed={"content": b"%PDF-whatever-scts-returns",
                                       "sha256": "ARBITRARY-SCTS-SHA", "size": 9})
        res = mod._retrieve_one(_D({"name": "PKG-1", "scts_document_id": "doc-1",
                                    "business_doctype": "EC Payment Request",
                                    "business_name": "PR-1"}), adapter, f, force=False)
        self.assertTrue(res.get("stored"))
        self.assertEqual(db.dsf["signed_file_sha256"], "ARBITRARY-SCTS-SHA",
                         "lan dau chap nhan bat ke sha - khong rang buoc voi ban ERP gui")
        # KHONG co phep so sanh nao voi f.sha256 (ban chua ky) - ghi nhan tin cay-mu.
        self.assertIn("SignedFileStored", ev.types())


if __name__ == "__main__":
    unittest.main()
