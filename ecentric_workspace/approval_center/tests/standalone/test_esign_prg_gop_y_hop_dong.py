# Copyright (c) 2026, eCentric and contributors
"""PR-G (23/11/2026): tra loi gop y cua chat Hop dong cho nen tang ky so.

  1. document_verification: PDF khong lop chu VAN goi ham doi chieu voi pages_text=[]; trang thai
     moi "not_applicable" = qua (cache nhu match, package_errors qua); "no_text" van chan.
  3. signing_files (hook ec_esign_signing_files): loai phieu khong khai -> None (DNTT nhu cu); ham
     loi / sai kieu -> fail-closed; package_errors: tep ky khong khai / thieu tep khai / khong lay
     duoc danh sach. document_setup: nguoi lap khong doi phan loai khi nghiep vu khai. requester:
     goi cua nguoi lap ky chi them tep khai.
  2. lifecycle.reopen_for_edit: dieu kien (Can bo sung, goi khoa, nguoi lap KHONG ky, chua ky,
     khong chan dang chay, khong mo ho); tao ban sua, bo tep khong con khai, danh dau huy tai
     lieu cu; provider_cancel quet goi Superseded co vet do (moi loai phieu), khong xet tu choi.
     document_setup._reopened_for_edit mo cua so sua. Retrieval bo goi Superseded / Cancelled.
  QC vong 1 (23/11): doi tac / nguoi ky da ky tren cong -> tu choi mo lai + provider_cancel khong
     huy goi Superseded co chu ky la; auto_place chi mo lai SAU moi phep kiem va khi tep khac ban
     da khoa; cua so sua theo vet; khoa phieu -> yeu cau duyet; tu huy tat -> tu choi khi con tai
     lieu; ham tep ky loi -> unreadable / tu choi; so sanh noi dung theo tep khai (tap con); PDF
     hong -> error (khong goi ham); khop tep ky theo noi dung (sha).
"""
import ast
import io
import json
import os
import sys
import textwrap
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


class _D(dict):
    __getattr__ = dict.get


class _Throw(Exception):
    pass


def _fns(src, names):
    out = []
    for n in ast.parse(src).body:
        nm = getattr(n, "name", None)
        if nm is None and isinstance(n, ast.Assign):
            nm = getattr(n.targets[0], "id", None)
        if nm in names:
            out.append(textwrap.dedent(ast.get_source_segment(src, n)))
    assert len(out) == len(names), (names, len(out))
    return "\n\n".join(out)


def _exec_mod(name, mods):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_m_" + name.replace(".", "_"))
        exec(compile(_read(name), name, "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m


class _Cache(object):
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v


# ================================================================== 1. document_verification
def _dv(fn, has_text=True):
    fk = types.ModuleType("frappe")
    cache = _Cache()
    fk.cache = lambda: cache
    fk.get_hooks = lambda name: {"EC Contract Review Request": ["biz.verify"]}
    fk.get_attr = lambda p: fn
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk.db = types.SimpleNamespace(get_value=lambda *a, **k: "2026-11-23 10:00")
    hs = types.ModuleType("hashing")
    import hashlib
    hs.sha256_bytes = lambda b: hashlib.sha256(b).hexdigest()
    pm = types.ModuleType("pdf_markers")
    pm.analyze = lambda c: {"ok": True, "has_text_layer": has_text,
                            "pages_text": ["HOP DONG SO 12"] if has_text else []}
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.hashing, root.pdf_markers = hs, pm
    m = _exec_mod("document_verification.py", {
        "frappe": fk, "ecentric_workspace.platform.esign": root,
        "ecentric_workspace.platform.esign.hashing": hs,
        "ecentric_workspace.platform.esign.pdf_markers": pm})
    m._cache = cache
    return m


BD = "EC Contract Review Request"


class TestVerify(unittest.TestCase):
    def test_khong_lop_chu_van_goi_ham(self):
        calls = []
        m = _dv(lambda *a: calls.append(a) or {"status": "not_applicable"}, has_text=False)
        r = m.verify(BD, "CTR-1", "scan.pdf", b"%PDF scan")
        self.assertEqual(r["status"], "not_applicable")
        self.assertFalse(r["has_text_layer"])
        self.assertEqual(calls, [(BD, "CTR-1", "scan.pdf", [])])

    def test_no_text_cua_ham_van_chan_cau_mac_dinh(self):
        m = _dv(lambda *a: {"status": "no_text"}, has_text=False)
        r = m.verify(BD, "CTR-1", "a.pdf", b"x")
        self.assertEqual(r["status"], "no_text")
        self.assertIn("Lưu thành PDF", r["reason"])

    def test_not_applicable_duoc_cache_nhu_match(self):
        n = []
        m = _dv(lambda *a: n.append(1) or {"status": "not_applicable"})
        m.verify(BD, "CTR-1", "a.pdf", b"x")
        m.verify(BD, "CTR-1", "a.pdf", b"x")
        self.assertEqual(len(n), 1)
        self.assertFalse(any(k.endswith(":err") for k in m._cache.d))

    def test_package_errors_qua_voi_not_applicable(self):
        m = _dv(lambda *a: {"status": "not_applicable"}, has_text=False)
        f = types.SimpleNamespace(name="DSF-1", file_name="scan.pdf")
        self.assertEqual(m.package_errors("P", BD, "CTR-1", [f], lambda x: b"x"), [])
        m2 = _dv(lambda *a: {"status": "no_text"}, has_text=False)
        self.assertEqual(m2.package_errors("P", BD, "CTR-1", [f], lambda x: b"x"),
                         ["document_verify:scan.pdf:no_text"])

    def test_trang_thai_la_thanh_loi(self):
        m = _dv(lambda *a: {"status": "ok"})
        self.assertEqual(m.verify(BD, "CTR-1", "a.pdf", b"x")["status"], "error")


# ================================================================== 3. signing_files
def _sf(hook=True, fn=None, files=None):
    fk = types.ModuleType("frappe")
    fk.get_hooks = lambda name: ({BD: ["biz.signing_files"]} if hook else {})
    fk.get_attr = lambda p: fn
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk.db = types.SimpleNamespace(get_value=lambda dt, n, f=None, **k: (files or {}).get(n))
    return _exec_mod("signing_files.py", {"frappe": fk})


class TestSigningFiles(unittest.TestCase):
    def test_khong_khai_thi_None(self):
        m = _sf(hook=False)
        self.assertIsNone(m.declared("EC Payment Request", "PR-1"))
        self.assertIsNone(m.is_signing_file("EC Payment Request", "PR-1", "/x.pdf"))
        self.assertEqual(m.package_errors("P", "EC Payment Request", "PR-1",
                                          [_D(requires_signature=1, file="F")]), [])

    def test_khai_va_loi_fail_closed(self):
        m = _sf(fn=lambda bn: ["/private/files/hd.pdf"])
        self.assertTrue(m.is_signing_file(BD, "CTR-1", "/private/files/hd.pdf"))
        self.assertFalse(m.is_signing_file(BD, "CTR-1", "/private/files/cccd.pdf"))
        for bad in (lambda bn: 1 / 0, lambda bn: "/private/files/hd.pdf", lambda bn: 5):
            d = _sf(fn=bad).declared(BD, "CTR-1")
            self.assertEqual(d["urls"], frozenset())
            self.assertTrue(d["error"])

    def test_package_errors(self):
        files = {"F1": "/private/files/hd.pdf", "F2": "/private/files/cu.pdf"}
        m = _sf(fn=lambda bn: ["/private/files/hd.pdf"], files=files)
        ok = [_D(requires_signature=1, file="F1", file_name="hd.pdf"),
              _D(requires_signature=0, file="F2", file_name="cu.pdf")]
        self.assertEqual(m.package_errors("P", BD, "CTR-1", ok), [])
        bad = [_D(requires_signature=1, file="F2", file_name="cu.pdf")]
        self.assertEqual(m.package_errors("P", BD, "CTR-1", bad),
                         ["signing_file_not_declared:cu.pdf", "signing_file_missing:1"])
        self.assertEqual(_sf(fn=lambda bn: 1 / 0).package_errors("P", BD, "CTR-1", ok),
                         ["signing_files_unavailable"])
        self.assertEqual(_sf(fn=lambda bn: []).package_errors("P", BD, "CTR-1", ok),
                         ["signing_files_unavailable"])


class TestReconcileDraft(unittest.TestCase):
    """QC PR-G vong 2 B-1: "mo lai TRUOC, tai ban moi SAU" - ban PDF cu con trong goi Draft phai bi
    go khi dat o / khoa goi, khong de goi ket voi tep nguoi lap khong go duoc."""

    def _m(self, pkg_status="Draft", fn=None):
        files = {"F-OLD": "/private/files/cu.pdf", "F-NEW": "/private/files/moi.pdf"}
        removed, events = [], []

        def gv(dt, n, f=None, **k):
            if dt == "EC Digital Signature Package":
                return pkg_status
            return files.get(n)
        fk = types.ModuleType("frappe")
        fk.get_hooks = lambda name: {BD: ["biz.signing_files"]}
        fk.get_attr = lambda p: fn or (lambda bn: ["/private/files/moi.pdf"])
        fk.log_error = lambda *a, **k: None
        fk.get_traceback = lambda: ""
        fk.session = types.SimpleNamespace(user="lap@x")
        fk.db = types.SimpleNamespace(get_value=gv)
        pk = types.ModuleType("pk")
        pk.package_files = lambda n: [
            _D(name="D-OLD", file="F-OLD", file_name="cu.pdf", requires_signature=1, sha256="S1"),
            _D(name="D-NEW", file="F-NEW", file_name="moi.pdf", requires_signature=1, sha256="S2"),
            _D(name="D-X", file="F-X", file_name="hoa_don.pdf", requires_signature=0)]
        pk.remove_file = lambda n: removed.append(n)
        pk.raw_file_bytes = lambda n: b"x"
        ev = types.ModuleType("ev")
        ev.emit = lambda et, **k: events.append(k.get("verification_result"))
        hs = types.ModuleType("hs")
        hs.sha256_bytes = lambda b: "S2"
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.package, root.events, root.hashing = pk, ev, hs
        m = _exec_mod("signing_files.py", {"frappe": fk})
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.package": pk,
                "ecentric_workspace.platform.esign.events": ev,
                "ecentric_workspace.platform.esign.hashing": hs}
        return m, mods, removed, events

    def _call(self, mods, fn, *a):
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            return fn(*a)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_go_ban_cu_khong_con_khai(self):
        m, mods, removed, events = self._m()
        out = self._call(mods, m.reconcile_draft, "PKG-NEW", BD, "CTR-1")
        self.assertEqual(out, ["cu.pdf"])
        self.assertEqual(removed, ["D-OLD"], "giu tep ky moi va bo chung tu")
        self.assertIn("signing_files_reconciled", events)

    def test_chi_goi_draft_va_khai_doc_duoc(self):
        m, mods, removed, _e = self._m(pkg_status="Locked")
        self.assertEqual(self._call(mods, m.reconcile_draft, "PKG", BD, "CTR-1"), [])
        m, mods, removed, _e = self._m(fn=lambda bn: 1 / 0)
        self.assertEqual(self._call(mods, m.reconcile_draft, "PKG", BD, "CTR-1"), [],
                         "ham khai loi -> khong go gi (preflight chan)")
        self.assertEqual(removed, [])

    def test_preflight_bo_qua_tep_se_bi_go(self):
        m, mods, _r, _e = self._m()
        files = [_D(file="F-OLD", file_name="cu.pdf", requires_signature=1, sha256="S1"),
                 _D(file="F-NEW", file_name="moi.pdf", requires_signature=1, sha256="S2")]
        kept = self._call(mods, m.signable_declared, BD, "CTR-1", files)
        self.assertEqual([f.file_name for f in kept], ["moi.pdf"])

    def test_khoa_goi_go_truoc_khi_chot(self):
        src = _read("package.py")
        seg = src[src.index("def lock_package("):src.index("def _repoint_profile(")]
        self.assertLess(seg.index("signing_files.reconcile_draft("),
                        seg.index("errs = preflight_for_lock(pkg_name)"))
        ps = _read("placement_service.py")
        sp = ps[ps.index("def save_placement("):ps.index("def delete_placement(")]
        self.assertIn("signing_files.reconcile_draft(cur_name", sp)


class TestWiring(unittest.TestCase):
    def test_moi_duong_them_tep_hoi_signing_files(self):
        ds = _read("document_setup.py")
        self.assertIn("can_classify = editable and is_requester and decl is None", ds)
        self.assertIn('return {"ok": False, "reason": "declared_by_business"}', ds)
        ps = _read("placement_service.py")
        self.assertEqual(ps.count("signing_files.is_signing_file("), 3,
                         "save_placement, _ensure_signable_dsf, auto_place")
        a = _read("api.py")
        self.assertEqual(a.count("signing_files.hook_path("), 2, "upload_package_file, set_file_flags")
        self.assertIn("signing_files.package_errors(", _read("package.py"))
        self.assertIn('decl is not None and (f.file_url or "") not in decl["urls"]',
                      _read("requester.py"))

    def test_create_revision_giu_slot(self):
        pk = _read("package.py")
        seg = pk[pk.index("def create_revision("):pk.index("def file_bytes(")]
        self.assertIn('"signer_slot_key": p.get("signer_slot_key")', seg)
        pl = pk[pk.index("def package_placements("):pk.index("def requester_placements_complete(")]
        self.assertIn('"signer_slot_key"', pl)

    def test_retrieval_bo_goi_superseded(self):
        t = _read("tasks.py")
        seg = t[t.index("def retrieve_signed_bundles("):t.index("def retrieve_signed_bundles(")
                + 2500]
        self.assertIn('"status": ["not in", ("Superseded", "Cancelled")]', seg)

    def test_api_post(self):
        a = _read("api.py")
        i = a.index("def reopen_signing_setup(")
        self.assertIn('@frappe.whitelist(methods=["POST"])', a[i - 60:i])


class TestAddRequesterPdf(unittest.TestCase):
    def test_chi_them_tep_khai(self):
        added = []
        files = [_D(name="F1", file_name="hd.pdf", file_url="/private/files/hd.pdf"),
                 _D(name="F2", file_name="cccd.pdf", file_url="/private/files/cccd.pdf")]
        fk = types.SimpleNamespace(get_all=lambda dt, **k: [] if dt != "File" else files)
        pk = types.SimpleNamespace(raw_file_bytes=lambda n: n.encode(),
                                   add_file=lambda p, d, c, **k: added.append(d))
        sf = types.ModuleType("sf")
        sf.declared = lambda bd, bn: {"urls": frozenset(["/private/files/hd.pdf"]), "error": None}
        root = types.ModuleType("ecentric_workspace.platform.esign")
        import hashlib
        hs = types.ModuleType("hashing")
        hs.sha256_bytes = lambda b: hashlib.sha256(b).hexdigest()
        root.signing_files, root.hashing = sf, hs
        g = {"frappe": fk, "pkgsvc": pk, "DSF": "DSF"}
        exec(compile(_fns(_read("requester.py"), ["_add_requester_pdf_files"]), "r", "exec"), g)
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.signing_files": sf,
                "ecentric_workspace.platform.esign.hashing": hs}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            n = g["_add_requester_pdf_files"]("PKG", BD, "CTR-1")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertEqual((n, added), (1, ["hd.pdf"]))


# ================================================================== QC: verify + signing sha
class TestVerifyQC(unittest.TestCase):
    def test_pdf_hong_la_loi_khong_goi_ham(self):
        calls = []
        m = _dv(lambda *a: calls.append(a) or {"status": "not_applicable"})
        r = m.verify(BD, "CTR-1", "x.pdf", b"x", analysis={"ok": False})
        self.assertEqual(r["status"], "error")
        self.assertEqual(calls, [], "PDF hong: khong goi ham (co the tra not_applicable)")
        self.assertTrue(all(k.endswith(":err") for k in m._cache.d))


class TestSigningSha(unittest.TestCase):
    def test_khop_theo_noi_dung(self):
        import hashlib
        fk = types.ModuleType("frappe")
        fk.get_hooks = lambda name: {BD: ["biz.sf"]}
        fk.get_attr = lambda p: (lambda bn: ["/private/files/hd.pdf"])
        fk.log_error = lambda *a, **k: None
        fk.get_traceback = lambda: ""
        fk.db = types.SimpleNamespace(get_value=lambda dt, n, f=None, **k: "F-HD")
        hs = types.ModuleType("hashing")
        hs.sha256_bytes = lambda b: hashlib.sha256(b).hexdigest()
        pk = types.ModuleType("package")
        pk.raw_file_bytes = lambda n: b"NOI DUNG HD"
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.hashing, root.package = hs, pk
        mods = {"frappe": fk, "ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.hashing": hs,
                "ecentric_workspace.platform.esign.package": pk}
        m = _exec_mod("signing_files.py", {"frappe": fk})
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            sha = hashlib.sha256(b"NOI DUNG HD").hexdigest()
            self.assertTrue(m.is_signing_file(BD, "C", "/private/files/hd-copy.pdf", sha=sha))
            self.assertFalse(m.is_signing_file(BD, "C", "/private/files/khac.pdf", sha="abc"))
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v


# ================================================================== 2. reopen_for_edit
class _World(object):
    def __init__(self, ar_status="Information Required", req_sig=0, signed=0, live=0,
                 err=None, user="lap@x", requester="lap@x", frozen=True, doc_id="DOC-1",
                 draft=None, bridge=0, external=0, signed_rows=(), portal_err=None,
                 armed=True, decl=None, opted=True, pre=None):
        self.__dict__.update(locals())
        self.events, self.revisions, self.removed, self.calls = [], [], [], []


def _lc(w, pkg_files=()):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=w.user)

    class Perm(Exception):
        pass
    fk.PermissionError = Perm

    def throw(m, exc=None):
        raise (exc or _Throw)(m)
    fk.throw = throw

    def get_value(dt, n, f=None, **k):
        w.calls.append((dt, f, bool(k.get("for_update"))))
        if dt == BD:
            return n
        if dt == "EC Approval Request":
            return n if f == "name" else w.ar_status
        if dt == "EC Digital Signature Profile":
            return w.external if f == "allow_external_signers" else w.req_sig
        if dt == "EC Digital Signature Package":
            if isinstance(n, dict):
                if n.get("status") == "Draft":
                    return w.draft
                if not w.frozen:
                    return None
                return _D(name="PKG-OLD", business_doctype=BD, business_name="CTR-1",
                          profile="P", scts_document_id=w.doc_id, error_code=w.err)
            return {"scts_document_id": w.doc_id}.get(f)
        return None

    def count(dt, f):
        if f.get("action") == "Sign":
            return w.signed
        if "transition_id" in f:
            return w.bridge
        if f.get("status") == "Approval Completed":
            return w.erp_done
        return w.live
    fk.db = types.SimpleNamespace(get_value=get_value, count=count)
    perms = types.ModuleType("perms")
    perms.business_approval_request = lambda bd, bn: "AR-1"
    perms.business_requested_by = lambda bd, bn: w.requester
    perms.assert_can_view_business = lambda bd, bn: w.calls.append(("view", bd, False))
    pk = types.ModuleType("pkgsvc")

    def create_revision(name):
        w.revisions.append(name)
        return _D(name="PKG-NEW")
    pk.create_revision = create_revision
    pk.package_files = lambda n: [_D(f) for f in pkg_files]
    pk.remove_file = lambda n: w.removed.append(n)
    ev = types.ModuleType("events")
    ev.emit = lambda et, **k: w.events.append((et, k.get("package"), k.get("verification_result")))
    sf = types.ModuleType("sf")
    sf.declared = lambda bd, bn: w.decl
    sf.hook_path = lambda bd: "biz.files" if w.opted else None
    sf.dsf_file_url = lambda f: f.get("url")
    sf.is_signing_file = lambda bd, bn, url, decl=None, sha=None: (
        None if decl is None else url in decl["urls"])
    pc = types.ModuleType("pc")
    pc.auto_armed = lambda: w.armed
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.permissions, root.signing_files, root.events, root.provider_cancel = perms, sf, ev, pc
    def portal_signed(name):
        w.calls.append(("portal", name, False))
        return (None, w.portal_err) if w.portal_err else (list(w.signed_rows), None)
    g = {"frappe": fk, "_": fk._, "pkgsvc": pk, "events": ev,
         "portal_signed_signers": portal_signed,
         "unmatched_signed": lambda name, signed: [x for x in signed or [] if x.get("stray")],
         "_portal_before_lock": lambda bd, bn: w.pre}
    src = _read("lifecycle.py")
    exec(compile(_fns(src, ["_FROZEN", "_IN_FLIGHT", "_lock_rows", "_reopen_check", "_REFUSE_VI",
                            "_UNSET", "reopen_for_edit", "maybe_reopen_for_edit", "_do_reopen",
                            "SUPERSEDED_FOR_EDIT"]), "lc", "exec"), g)
    mods = {"ecentric_workspace.platform.esign": root,
            "ecentric_workspace.platform.esign.permissions": perms,
            "ecentric_workspace.platform.esign.signing_files": sf,
            "ecentric_workspace.platform.esign.provider_cancel": pc}

    def run(fn_name):
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            return g[fn_name](BD, "CTR-1")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
    return run, Perm


class TestReopen(unittest.TestCase):
    def test_mo_lai_tao_ban_sua_va_danh_dau_huy(self):
        w = _World(decl={"urls": frozenset(["/new.pdf"]), "error": None})
        run, _P = _lc(w, pkg_files=[{"name": "D1", "requires_signature": 1, "url": "/old.pdf",
                                     "file_name": "old.pdf"},
                                    {"name": "D2", "requires_signature": 1, "url": "/new.pdf",
                                     "file_name": "new.pdf"},
                                    {"name": "D3", "requires_signature": 0, "url": "/x.xlsx"}])
        r = run("reopen_for_edit")
        self.assertTrue(r["reopened"])
        self.assertEqual((r["new_package"], r["old_package"]), ("PKG-NEW", "PKG-OLD"))
        self.assertTrue(r["cancel_pending"])
        self.assertEqual(w.revisions, ["PKG-OLD"])
        self.assertEqual(w.removed, ["D1"], "bo tep ky cu khong con khai, giu bo chung tu")
        self.assertIn(("PollTick", "PKG-OLD", "superseded_for_edit"), w.events)
        self.assertIn(("PollTick", "PKG-NEW", "reopened_for_edit"), w.events)

    def test_khoa_phieu_roi_yeu_cau_duyet_doc_co_khoa(self):
        w = _World()
        run, _P = _lc(w)
        run("reopen_for_edit")
        locks = [(c[0], c[1]) for c in w.calls if c[2]]
        self.assertEqual(locks[:2], [(BD, "name"), ("EC Approval Request", "name")],
                         "cung thu tu voi auto_place / Gui lai")
        self.assertIn(("EC Approval Request", "approval_status", True), w.calls,
                      "trang thai doc CO KHOA (khong anh chup cu)")

    def test_khong_tai_lieu_tren_cong_thi_khong_danh_dau_huy(self):
        w = _World(doc_id=None, armed=False)
        run, _P = _lc(w)
        r = run("reopen_for_edit")
        self.assertFalse(r["cancel_pending"])
        self.assertNotIn("superseded_for_edit", [e[2] for e in w.events])

    def test_tu_choi(self):
        cases = (({"signed": 1}, "Từ chối"), ({"live": 1}, "chờ vài phút"),
                 ({"err": "create_outcome_unknown"}, "đối soát"),
                 ({"bridge": 1}, "Đối tác"),
                 ({"signed_rows": [{"stray": 1, "is_external": True}]}, "Đối tác"),
                 ({"signed_rows": [{"user_id": "U1"}, {"stray": 1}]}, "Đối tác"),
                 ({"portal_err": "Timeout"}, "Chưa đọc được"),
                 ({"armed": False}, "tự huỷ đang tắt"),
                 ({"decl": {"urls": frozenset(), "error": "TypeError"}}, "lỗi hệ thống"))
        for kw, word in cases:
            w = _World(**kw)
            run, _P = _lc(w)
            with self.assertRaises(_Throw, msg=kw) as cm:
                run("reopen_for_edit")
            self.assertIn(word, str(cm.exception), kw)
            self.assertEqual(w.revisions, [], kw)

    def test_khong_doc_duoc_cong_luon_chan_khop_danh_tinh_thi_mo(self):
        """QC vong 2: khong doc duoc cong -> CHAN (ke ca ho so khong doi tac); moi nguoi da ky khop
        danh tinh chan ERP -> mo duoc."""
        w = _World(external=0, portal_err="Timeout")
        run, _P = _lc(w)
        with self.assertRaises(_Throw):
            run("reopen_for_edit")
        w = _World(signed_rows=[{"user_id": "U-KTTH"}])
        run, _P = _lc(w)
        self.assertTrue(run("reopen_for_edit")["reopened"], "chu ky cong = chan ERP biet")

    def test_doc_cong_truoc_khi_khoa(self):
        """QC vong 2 minor 1: ket qua doc cong truoc khoa duoc dung lai, khong goi mang khi giu khoa."""
        w = _World(pre=("PKG-OLD", "DOC-1", [{"user_id": "U-KTTH"}], None))
        run, _P = _lc(w)
        self.assertTrue(run("reopen_for_edit")["reopened"])
        self.assertNotIn("portal", [c[0] for c in w.calls])
        w = _World(pre=("PKG-OLD", "DOC-1", [{"stray": 1}], None))
        run, _P = _lc(w)
        with self.assertRaises(_Throw):
            run("reopen_for_edit")
        w = _World(pre=("PKG-OLD", "DOC-CU", [], None))
        run, _P = _lc(w)
        run("reopen_for_edit")
        self.assertIn("portal", [c[0] for c in w.calls], "tai lieu doi trong luc cho -> doc lai")

    def test_chi_loai_phieu_khai_tep_ky(self):
        """QC vong 2 M-3: loai phieu khong khai ec_esign_signing_files (DNTT) khong bao gio mo lai."""
        w = _World(opted=False)
        run, _P = _lc(w)
        self.assertIsNone(run("maybe_reopen_for_edit"))
        with self.assertRaises(_Throw) as cm:
            run("reopen_for_edit")
        self.assertIn("không hỗ trợ", str(cm.exception))
        self.assertEqual(w.revisions, [])

    def test_khong_phai_truong_hop_nay(self):
        for kw in ({"ar_status": "Pending"}, {"req_sig": 1}, {"frozen": False}):
            w = _World(**kw)
            run, _P = _lc(w)
            self.assertIsNone(run("maybe_reopen_for_edit"), kw)
            with self.assertRaises(_Throw):
                run("reopen_for_edit")
        w = _World(frozen=False, draft="PKG-D")
        run, _P = _lc(w)
        self.assertEqual(run("reopen_for_edit")["reason"], "already_draft")

    def test_chi_nguoi_lap(self):
        w = _World(user="khac@x")
        run, Perm = _lc(w)
        with self.assertRaises(Perm):
            run("reopen_for_edit")
        self.assertEqual([c for c in w.calls if c[2]], [],
                         "QC vong 2: tu choi TRUOC khi khoa / doc trang thai")
        self.assertIsNone(run("maybe_reopen_for_edit"))

    def test_maybe_bao_ly_do_khi_bi_chan(self):
        w = _World(signed=1)
        run, _P = _lc(w)
        with self.assertRaises(_Throw):
            run("maybe_reopen_for_edit")


class TestPortalSignatures(unittest.TestCase):
    def _run(self, signers=None, boom=False, doc="DOC", enabled=1):
        fk = types.SimpleNamespace(db=types.SimpleNamespace(
            get_value=lambda *a, **k: _D(scts_document_id=doc, provider="SCTS",
                                         environment="UAT")))
        pc = types.ModuleType("pc")
        pc._settings = lambda p, e: {"integration_enabled": enabled}
        prov = types.ModuleType("prov")

        class Ad(object):
            def poll_status(self, d):
                if boom:
                    raise RuntimeError("x")
                return types.SimpleNamespace(signers=signers or [])
        prov.get_adapter = lambda s: Ad()
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.provider_cancel = pc
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.provider_cancel": pc,
                "ecentric_workspace.platform.esign.providers": prov}
        g = {"frappe": fk}
        exec(compile(_fns(_read("lifecycle.py"), ["portal_signed_signers"]), "p", "exec"), g)
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            return g["portal_signed_signers"]("PKG")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_doc(self):
        s = [{"status": "signed", "is_external": True}, {"status": "pending"},
             {"status": "signed", "is_external": False}]
        rows, err = self._run(s)
        self.assertEqual((len(rows), err), (2, None))
        self.assertEqual(self._run(doc=None), ([], None))
        self.assertEqual(self._run(boom=True), (None, "RuntimeError"))
        self.assertEqual(self._run(enabled=0), (None, "integration_closed"))


class TestUnmatchedSigned(unittest.TestCase):
    """QC vong 2 M-4: doi chieu nguoi da ky tren cong theo DANH TINH chan ERP da xong."""

    def _u(self, dsrs, signed):
        fk = types.SimpleNamespace(get_all=lambda dt, **k: [_D(x) for x in dsrs])
        svc = types.ModuleType("svc")
        svc._emails_cua_cung_danh_tinh = lambda d: {
            "U-KTT": ["ktt@ec", "ktt2@ec"]}.get(d.get("effective_scts_user_id"), [])
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.service = svc
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.service": svc}
        g = {"frappe": fk}
        exec(compile(_fns(_read("lifecycle.py"), ["unmatched_signed"]), "u", "exec"), g)
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            return g["unmatched_signed"]("PKG", signed)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_khop(self):
        d = [{"effective_scts_user_id": "U-KTT", "actor_user": None, "approver": "ktt@ec"}]
        self.assertEqual(self._u(d, [{"user_id": "U-KTT"}]), [])
        self.assertEqual(self._u(d, [{"user_id": None, "email": "KTT2@ec"}]), [], "email cung danh tinh")

    def test_khong_khop(self):
        d = [{"effective_scts_user_id": "U-KTT", "actor_user": None, "approver": "ktt@ec"}]
        self.assertEqual(len(self._u(d, [{"user_id": "U-LA", "email": "la@x"}])), 1)
        self.assertEqual(len(self._u(d, [{"user_id": "U-KTT", "is_external": True}])), 1,
                         "doi tac ngoai luon chan")
        self.assertEqual(len(self._u([], [{"user_id": "U-KTT"}])), 1, "chua chan ERP nao xong")


class TestContentVerdict(unittest.TestCase):
    def _v(self, locked, present, decl, declared=None, before=False):
        pk = types.SimpleNamespace(package_files=lambda n: [
            _D(requires_signature=1, sha256=x) for x in locked])
        g = {"pkgsvc": pk, "_attached_signable_shas": lambda pkg, d=None: set(present),
             "_declared_shas_strict": lambda d: (None if declared == "X"
                                                 else set(declared if declared is not None
                                                          else present)),
             "_locked_before_signing_files": lambda pkg: before}
        exec(compile(_fns(_read("lifecycle.py"), ["_signable_content_verdict"]), "v", "exec"), g)
        return g["_signable_content_verdict"](_D(name="P"), decl)

    def test_khai_tep_ky(self):
        d = {"urls": frozenset(["/hd.pdf"]), "error": None}
        self.assertEqual(self._v(["A"], [], d, declared=["A"]), "unchanged")
        self.assertEqual(self._v(["A", "B"], [], d, declared=["A"]), "changed",
                         "QC vong 2: bo tep khai BOT so voi goi khoa = da doi")
        self.assertEqual(self._v(["A", "B"], [], d, declared=["A"], before=True), "unchanged",
                         "goi khoa TRUOC hook (luat cu) - tap con van 'khong doi'")
        self.assertEqual(self._v(["A"], [], d, declared=["C"]), "changed")
        self.assertEqual(self._v(["A"], [], d, declared=[]), "changed")
        self.assertEqual(self._v(["A"], [], d, declared="X"), "unreadable")
        self.assertEqual(self._v(["A"], ["A"], {"urls": frozenset(), "error": "X"}), "unreadable")
        self.assertEqual(self._v(["A"], ["A", "C"], None), "unchanged", "DNTT nhu cu")

    def test_doc_tep_khai_theo_url_ke_ca_cong_khai(self):
        src = _read("lifecycle.py")
        seg = src[src.index("def _declared_shas_strict("):src.index("def _attached_signable_shas(")]
        self.assertNotIn("is_private", seg)


class TestResubmitRestart(unittest.TestCase):
    def test_goi_mo_lai_thi_chay_lai_tu_cap_1(self):
        def run(draft, ev):
            fk = types.SimpleNamespace(
                db=types.SimpleNamespace(get_value=lambda *a, **k: draft),
                get_all=lambda dt, **k: [_D(name="E")] if ev else [])
            g = {"frappe": fk, "_frozen_package": lambda ar: None,
                 "pkgsvc": types.SimpleNamespace(preflight_for_lock=lambda n: [])}
            src = _read("lifecycle.py")
            exec(compile(_fns(src, ["_reopened_draft", "on_request_reopened",
                                    "_assert_reopened_draft_ready"]), "l", "exec"), g)
            return g["on_request_reopened"]("AR-1")
        self.assertEqual(run("PKG-NEW", True),
                         {"revised": True, "new_package": "PKG-NEW", "force_restart": True,
                          "reason": "reopened_for_edit"})
        self.assertFalse(run("PKG-D", False)["force_restart"], "Draft thuong (chua gui) nhu cu")
        self.assertFalse(run(None, False)["revised"])

    def test_goi_mo_lai_thieu_o_thi_tu_choi_gui_lai(self):
        """QC vong 2 M-2: goi Draft mo lai chua san sang -> TU CHOI gui lai (khong de phieu Pending
        khong co goi ky de khoa)."""
        req = types.ModuleType("req")
        req._preflight_vi = lambda e: "VI:" + e
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.requester = req

        def throw(m, exc=None):
            raise _Throw(m)
        fk = types.SimpleNamespace(
            db=types.SimpleNamespace(get_value=lambda *a, **k: "PKG-NEW"),
            get_all=lambda dt, **k: [_D(name="E")], throw=throw)
        g = {"frappe": fk, "_": lambda s: s, "_frozen_package": lambda ar: None,
             "pkgsvc": types.SimpleNamespace(
                 preflight_for_lock=lambda n: ["missing_placement:L4:hd.pdf"])}
        exec(compile(_fns(_read("lifecycle.py"), ["_reopened_draft", "on_request_reopened",
                                                  "_assert_reopened_draft_ready"]),
                     "l", "exec"), g)
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.requester": req}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            with self.assertRaises(_Throw) as cm:
                g["on_request_reopened"]("AR-1")
            self.assertIn("VI:missing_placement", str(cm.exception))
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_luoi_an_toan_chi_tinh_chan_cua_goi_hien_tai(self):
        src = io.open(os.path.join(_ESIGN, "portal_steps.py"), encoding="utf-8").read()
        seg = src[src.index("def sweep_missing_requester_steps("):src.index("def complete_requester_step(")]
        self.assertIn("pk.status NOT IN ('Superseded', 'Cancelled')", seg)

    def test_ghi_chu_cap_1_dung_ly_do(self):
        path = os.path.join(_APP, "ecentric_workspace", "approval_center", "shared", "workflow",
                            "transitions.py")
        with io.open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('esign.get("reason") == "reopened_for_edit"', src)


class TestSetupWindow(unittest.TestCase):
    def _f(self, ar_status, req_sig, marked="PKG-D"):
        def gv(dt, n, f=None, **k):
            if dt == "EC Approval Request":
                return ar_status
            if dt == "EC Digital Signature Package":
                return "P"
            return req_sig
        lc = types.ModuleType("lc")
        lc._reopened_draft = lambda ar: marked
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.lifecycle = lc
        g = {"frappe": types.SimpleNamespace(db=types.SimpleNamespace(get_value=gv)),
             "AR": "EC Approval Request", "PKG": "EC Digital Signature Package"}
        exec(compile(_fns(_read("document_setup.py"), ["_reopened_for_edit"]), "d", "exec"), g)
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.lifecycle": lc}

        def call(ar, draft):
            saved = {k: sys.modules.get(k) for k in mods}
            sys.modules.update(mods)
            try:
                return g["_reopened_for_edit"](ar, draft)
            finally:
                for k, v in saved.items():
                    if v is None:
                        sys.modules.pop(k, None)
                    else:
                        sys.modules[k] = v
        return call

    def test_mo_chi_khi_dung_goi_co_vet(self):
        self.assertTrue(self._f("Information Required", 0)("AR", "PKG-D"))
        self.assertFalse(self._f("Information Required", 0, marked=None)("AR", "PKG-D"),
                         "Draft khong co vet (gui truoc PR-C) khong mo")
        self.assertFalse(self._f("Information Required", 0, marked="PKG-X")("AR", "PKG-D"))
        self.assertFalse(self._f("Information Required", 1)("AR", "PKG-D"), "DNTT nhu cu")
        self.assertFalse(self._f("Pending", 0)("AR", "PKG-D"))
        self.assertFalse(self._f("Information Required", 0)("AR", None))


# ================================================================== auto_place
class _APW(object):
    def __init__(self, sig=True, pdf=True, verify="match", locked=None, sha="SHA-NEW",
                 markers=True, allowed=True):
        self.__dict__.update(locals())
        self.reopened, self.write_checked, self.order = [], [], []


def _ap(w):
    fk = types.SimpleNamespace(db=types.SimpleNamespace(
        rollback=lambda: None, get_value=lambda *a, **k: "X"))
    def can_classify(bd, bn):
        w.order.append("perm")
        if not w.allowed:
            raise _Throw("not requester")
    ds = types.SimpleNamespace(_is_pdf_name=lambda n, u: w.pdf, _assert_can_classify=can_classify)
    def raw(n):
        w.order.append("read")
        return b"pdf"
    pk = types.SimpleNamespace(raw_file_bytes=raw,
                               hashing=types.SimpleNamespace(sha256_bytes=lambda b: w.sha))
    sf = types.SimpleNamespace(is_signing_file=lambda bd, bn, url, sha=None, decl=None: w.sig,
                               hook_path=lambda bd: "x",
                               reconcile_draft=lambda pkg, bd, bn: w.order.append(
                                   "reconcile:%s" % pkg) or [])
    dv = types.ModuleType("dv")
    dv.PASS_STATUSES = ("match", "not_applicable")
    dv.verifier_path = lambda bd: "biz.v"

    def verify(*a, **k):
        w.order.append("verify")
        return {"status": w.verify, "reason": "r"}
    dv.verify = verify
    pm = types.ModuleType("pm")
    pm.analyze = lambda c: {"ok": True, "markers": [{"name": "KY_BEN_A", "page_index": 1}]
                            if w.markers else [], "skipped": []}
    pm.box_for = lambda m: {"page_index": 1, "x": 1, "y": 1, "width": 1, "height": 1}
    lc = types.ModuleType("lc")
    lc.locked_signable_shas = lambda bd, bn: w.locked

    def reopen(bd, bn, portal=None):
        w.order.append("reopen")
        w.reopened.append(1)
        w.portal_passed = portal
        return {"new_package": "PKG-NEW"}
    lc.maybe_reopen_for_edit = reopen

    def pre_portal(bd, bn):
        w.order.append("portal")
        return ("PKG-OLD", "DOC-1", [], None)
    lc.portal_for_possible_reopen = pre_portal
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.document_verification, root.pdf_markers, root.lifecycle = dv, pm, lc

    def write_ok(bd, bn):
        w.order.append("write_ok")
        return "PKG-NEW"
    g = {"frappe": fk, "ds": ds, "pkgsvc": pk, "signing_files": sf,
         "_resolve_file": lambda bd, bn, ref: _D(name="F1", file_name="hd.pdf",
                                                  file_url="/hd.pdf"),
         "_assert_write_ok": write_ok,
         "_required_slots": lambda bd, bn: ([], [], {}),
         "_marker_slots": lambda bd, bn, r: {"KY_BEN_A": "S1"},
         "placement_state": lambda bd, bn, ref: {"placements": []},
         "save_placement": lambda bd, bn, ref, box: {"ok": True}}
    exec(compile(_fns(_read("placement_service.py"), ["auto_place"]), "ap", "exec"), g)
    mods = {"ecentric_workspace.platform.esign": root,
            "ecentric_workspace.platform.esign.document_verification": dv,
            "ecentric_workspace.platform.esign.pdf_markers": pm,
            "ecentric_workspace.platform.esign.lifecycle": lc}

    def run():
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            return g["auto_place"](BD, "CTR-1", "F1")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
    return run


class TestAutoPlaceReopen(unittest.TestCase):
    def test_tep_hong_khong_mo_lai(self):
        for kw, why in (({"sig": False}, "not_signing_file"), ({"pdf": False}, "not_pdf"),
                        ({"verify": "mismatch"}, "verify_mismatch"),
                        ({"verify": "no_text"}, "verify_no_text"),
                        ({"verify": "error"}, "verify_error")):
            w = _APW(locked={"SHA-OLD"}, **kw)
            r = _ap(w)()
            self.assertEqual((r["ok"], r["reason"]), (False, why), kw)
            self.assertEqual(w.reopened, [], kw)

    def test_tep_trung_ban_da_khoa_khong_mo_lai(self):
        w = _APW(locked={"SHA-NEW"})
        r = _ap(w)()
        self.assertEqual(r["reason"], "unchanged_in_locked_package")
        self.assertEqual(w.reopened, [])

    def test_tep_moi_qua_kiem_thi_mo_lai_roi_dat(self):
        w = _APW(locked={"SHA-OLD"})
        r = _ap(w)()
        self.assertEqual(w.order[:8], ["perm", "portal", "perm", "read", "verify", "reopen",
                                       "write_ok", "reconcile:PKG-NEW"])
        self.assertEqual(w.portal_passed, ("PKG-OLD", "DOC-1", [], None),
                         "ket qua doc cong TRUOC khoa duoc chuyen vao, khong doc lai khi giu khoa")
        self.assertEqual(r["reopened"], "PKG-NEW")
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["placed"]), 1)

    def test_not_applicable_ok_false_keo_tay(self):
        w = _APW(locked={"SHA-OLD"}, verify="not_applicable")
        r = _ap(w)()
        self.assertEqual((r["ok"], r["reason"]), (False, "manual_placement"))
        self.assertEqual(w.reopened, [1], "van mo lai de nguoi lap keo o tay")

    def test_quyen_truoc_moi_lan_doc(self):
        """QC vong 2 M-1: khong phai nguoi lap -> tu choi TRUOC khi doc / doi chieu tep."""
        w = _APW(locked={"SHA-OLD"}, allowed=False)
        with self.assertRaises(_Throw):
            _ap(w)()
        self.assertEqual(w.order, ["perm"])

    def test_khong_phai_can_bo_sung_khong_mo_lai(self):
        w = _APW(locked=None)
        r = _ap(w)()
        self.assertTrue(r["ok"])
        self.assertEqual(w.reopened, [])


# ================================================================== provider_cancel
class TestProviderCancelRevision(unittest.TestCase):
    def _check(self, pkg, marked=True, live=()):
        g = {"AUTO_DOCTYPES": ("EC Payment Request",), "ACTIVE_PKG": ("Active", "Locked"),
             "NEGATIVE": ("Rejected", "Cancelled"), "SUPERSEDED_FOR_EDIT": "superseded_for_edit",
             "EVT": "EVT", "frappe": types.SimpleNamespace(
                 get_all=lambda dt, **k: [_D(name="E")] if marked else [])}
        exec(compile(_fns(_read("provider_cancel.py"), ["_superseded_for_edit", "_check_pkg"]),
                     "pc", "exec"), g)
        g["_live_legs"] = lambda n: list(live)
        return g["_check_pkg"](pkg, _D(approval_status="Pending"))

    def test_goi_superseded_co_vet_duoc_huy_moi_loai_phieu(self):
        pkg = _D(name="P1", status="Superseded", business_doctype=BD, scts_document_id="DOC",
                 error_code=None, signed_bundle_complete=0)
        self.assertIsNone(self._check(pkg))
        self.assertEqual(self._check(pkg, marked=False), "package_status:Superseded")
        self.assertTrue(self._check(pkg, live=[_D(name="L", status="Queued")]).startswith(
            "live_legs"))

    def test_dntt_superseded_khong_vet_khong_huy(self):
        pkg = _D(name="P3", status="Superseded", business_doctype="EC Payment Request",
                 scts_document_id="DOC", error_code=None, signed_bundle_complete=0)
        self.assertEqual(self._check(pkg, marked=False), "package_status:Superseded")

    def test_phieu_song_khong_superseded_van_can_tu_choi(self):
        pkg = _D(name="P2", status="Active", business_doctype="EC Payment Request",
                 scts_document_id="DOC", error_code=None, signed_bundle_complete=0)
        self.assertTrue(self._check(pkg).startswith("request_not_rejected"))

    def test_ung_vien_chi_goi_co_vet(self):
        calls = []

        def get_all(dt, filters=None, **k):
            calls.append((dt, filters))
            if dt == "EVT":
                return [_D(package="P1"), _D(package="P1"), _D(package="P9")]
            return [_D(name="P1", business_name="C1", error_code=None)]
        g = {"EVT": "EVT", "PKG": "PKG", "SUPERSEDED_FOR_EDIT": "superseded_for_edit",
             "frappe": types.SimpleNamespace(get_all=get_all),
             "_skipped": lambda n: n == "P9"}
        exec(compile(_fns(_read("provider_cancel.py"), ["_revision_candidates"]), "rc", "exec"), g)
        rows = g["_revision_candidates"]()
        self.assertEqual([r.name for r in rows], ["P1"])
        pkg_filter = [f for dt, f in calls if dt == "PKG"][0]
        self.assertEqual(pkg_filter["name"], ["in", ["P1"]], "khong trung, bo goi da bo qua")
        self.assertEqual(pkg_filter["status"], "Superseded")

    def _cancel(self, signers, erp_ids=(), status="Superseded"):
        st = types.SimpleNamespace(signers=signers, identity={})
        pkg = _D(name="P1", status=status, business_name="C1", scts_document_id="DOC",
                 approval_request="AR", provider="SCTS", environment="UAT")
        lc = types.ModuleType("lc")
        lc.unmatched_signed = lambda name, rows: [x for x in rows if x.get("is_external")
                                                  or x.get("user_id") not in erp_ids]
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.lifecycle = lc
        self._mods = {"ecentric_workspace.platform.esign": root,
                      "ecentric_workspace.platform.esign.lifecycle": lc}
        g = {"frappe": types.SimpleNamespace(db=types.SimpleNamespace(
                count=lambda dt, f: 0), session=types.SimpleNamespace(user="x")),
             "DSR": "DSR", "SOURCE_SM": "sm", "ProviderError": Exception,
             "_pkg": lambda n: pkg, "_check_pkg": lambda p, a: None,
             "_ar": lambda n: _D(approval_status="Information Required"),
             "_settings": lambda p, e: {"integration_enabled": 1},
             "get_adapter": lambda s: types.SimpleNamespace(poll_status=lambda d: st,
                                                            cancel_document=lambda *a: None),
             "_state_status": lambda s: "processing", "_transient": lambda c: False,
             "_prior_sent": lambda n: False, "_lock": lambda n: "K", "_unlock": lambda k: None}
        exec(compile(_fns(_read("provider_cancel.py"), ["cancel_one"]), "c", "exec"), g)
        saved = {k: sys.modules.get(k) for k in self._mods}
        sys.modules.update(self._mods)
        try:
            return g["cancel_one"]("P1", dry_run=True)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_superseded_co_chu_ky_la_khong_huy(self):
        r = self._cancel([{"status": "signed", "is_external": True, "user_id": "P"},
                          {"status": "pending"}])
        self.assertEqual(r["result"], "stop")
        self.assertTrue(r["reason"].startswith("superseded_signed_on_portal:1/1:external"))
        r = self._cancel([{"status": "signed", "user_id": "U-LA"}, {"status": "pending"}],
                         erp_ids=("U-KTT",))
        self.assertTrue(r["reason"].startswith("superseded_signed_on_portal:1/1"),
                        "QC vong 2 M-4: so theo danh tinh, khong dem")
        r = self._cancel([{"status": "signed", "user_id": "U-KTT"}, {"status": "pending"}],
                         erp_ids=("U-KTT",))
        self.assertEqual(r["result"], "would_cancel", "chu ky cong = chan ERP biet -> huy duoc")
        r = self._cancel([{"status": "signed", "is_external": True}, {"status": "pending"}],
                         status="Active")
        self.assertEqual(r["result"], "would_cancel", "phieu tu choi (khong Superseded) nhu cu")


# ================================================================== api + document_setup
class TestApiDeclared(unittest.TestCase):
    def test_set_file_flags_tu_choi_khi_khai(self):
        sf = types.ModuleType("sf")
        sf.hook_path = lambda bd: "x" if bd == BD else None
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.signing_files = sf
        called = []

        def gv(dt, n, f=None, **k):
            return "PKG" if dt == "EC Digital Signature File" else w_bd[0]
        w_bd = [BD]
        g = {"frappe": types.SimpleNamespace(db=types.SimpleNamespace(get_value=gv),
                                             throw=lambda m: (_ for _ in ()).throw(_Throw(m))),
             "_": lambda s: s,
             "pkgsvc": types.SimpleNamespace(set_file_flags=lambda *a: called.append(a) or "ok")}
        exec(compile(_fns(_read("api.py"), ["set_file_flags"]), "a", "exec"), g)
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.signing_files": sf}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            with self.assertRaises(_Throw):
                g["set_file_flags"]("DSF", requires_signature=1)
            self.assertEqual(g["set_file_flags"]("DSF", share_with_partner=1), "ok")
            w_bd[0] = "EC Payment Request"
            self.assertEqual(g["set_file_flags"]("DSF", requires_signature=0), "ok", "DNTT nhu cu")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v


class TestReopenHint(unittest.TestCase):
    def test_goi_y(self):
        def mk(ar_status, req_sig):
            def gv(dt, n, f=None, **k):
                if dt == "EC Approval Request":
                    return ar_status
                if dt == "EC Digital Signature Package":
                    return "P"
                return req_sig
            g = {"frappe": types.SimpleNamespace(db=types.SimpleNamespace(get_value=gv)),
                 "AR": "EC Approval Request", "PKG": "EC Digital Signature Package",
                 "perms": types.SimpleNamespace(business_approval_request=lambda bd, bn: "AR"),
                 "_current_package": lambda bd, bn: ("PKG-OLD", "Locked", False, False)}
            exec(compile(_fns(_read("document_setup.py"), ["_reopen_hint"]), "h", "exec"), g)
            sf = types.ModuleType("sf")
            sf.hook_path = lambda bd: "x" if bd == BD else None
            root = types.ModuleType("ecentric_workspace.platform.esign")
            root.signing_files = sf
            mods = {"ecentric_workspace.platform.esign": root,
                    "ecentric_workspace.platform.esign.signing_files": sf}
            saved = {k: sys.modules.get(k) for k in mods}
            sys.modules.update(mods)
            try:
                return g["_reopen_hint"](BD, "C"), g["_reopen_hint"]("EC Payment Request", "C")
            finally:
                for k, v in saved.items():
                    if v is None:
                        sys.modules.pop(k, None)
                    else:
                        sys.modules[k] = v
        self.assertEqual(mk("Information Required", 0), (True, False),
                         "QC vong 2 M-3: chi loai phieu khai tep ky")
        self.assertFalse(mk("Information Required", 1)[0])
        self.assertFalse(mk("Pending", 0)[0])
        self.assertNotIn("Thay bản PDF", _read("document_setup.py"),
                         "QC vong 2 minor 5: khong ghi cung nhan nut cua nghiep vu")


# --------------------------------------------------------------------------- QC vong 3
class TestFirstSeen(unittest.TestCase):
    """M3: moc "goi khoa truoc khi co hook" ghi khi declared() thanh cong lan dau - khong ngay cung."""

    def _m(self, store, fn=lambda bn: ["/f.pdf"]):
        m = _sf(fn=fn)
        m.frappe.db.get_default = lambda k: store.get(k)
        m.frappe.db.set_default = lambda k, v: store.__setitem__(k, v)
        fu = types.ModuleType("frappe.utils")
        fu.now_datetime = lambda: "2026-11-25 08:00:00"
        sys.modules["frappe.utils"] = fu
        return m

    def tearDown(self):
        sys.modules.pop("frappe.utils", None)

    def test_ghi_mot_lan_khong_ghi_de(self):
        store = {}
        m = self._m(store)
        m.declared(BD, "CTR-1")
        key = m.FIRST_SEEN_KEY % BD
        self.assertEqual(store[key], "2026-11-25 08:00:00")
        store[key] = "2026-11-20 00:00:00"
        m.declared(BD, "CTR-2")
        self.assertEqual(store[key], "2026-11-20 00:00:00", "khong ghi de moc cu")
        self.assertEqual(m.first_seen(BD), "2026-11-20 00:00:00")

    def test_hook_loi_khong_ghi(self):
        store = {}
        def boom(bn):
            raise ValueError("x")
        m = self._m(store, fn=boom)
        self.assertTrue(m.declared(BD, "CTR-1")["error"])
        self.assertEqual(store, {})


class TestLockedBefore(unittest.TestCase):
    def _run(self, locked_at, since):
        sf = types.SimpleNamespace(first_seen=lambda bd: since)
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.signing_files = sf
        fk = types.SimpleNamespace(db=types.SimpleNamespace(
            get_value=lambda dt, n, f=None, **k: locked_at))
        g = {"frappe": fk}
        exec(compile(_fns(_read("lifecycle.py"), ["_locked_before_signing_files"]), "l", "exec"), g)
        saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                                 "ecentric_workspace.platform.esign.signing_files")}
        sys.modules["ecentric_workspace.platform.esign"] = root
        sys.modules["ecentric_workspace.platform.esign.signing_files"] = sf
        try:
            return g["_locked_before_signing_files"](_D(name="P", business_doctype=BD))
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_theo_moc_lan_dau_thay_hook(self):
        self.assertTrue(self._run("2026-11-24 10:00:00", "2026-11-26 09:00:00"))
        self.assertFalse(self._run("2026-11-27 10:00:00", "2026-11-26 09:00:00"))
        self.assertTrue(self._run("2026-11-27 10:00:00", None), "chua co moc -> goi cu (tap con)")
        self.assertFalse(self._run(None, "2026-11-26 09:00:00"))

    def test_khong_con_ngay_ghi_cung(self):
        self.assertNotIn("SIGNING_FILES_SINCE", _read("lifecycle.py"))


class TestPortalBeforeLockSkip(unittest.TestCase):
    """Minor 4: khong goi CMC khi phieu khong o "Can bo sung"."""

    def _run(self, status):
        calls = []
        perms = types.SimpleNamespace(business_approval_request=lambda bd, bn: "AR-1")
        sf = types.SimpleNamespace(hook_path=lambda bd: "x")
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.permissions, root.signing_files = perms, sf
        fk = types.SimpleNamespace(db=types.SimpleNamespace(
            get_value=lambda dt, n, f=None, **k: status if f == "approval_status" else "DOC-1"))
        g = {"frappe": fk, "_frozen_package": lambda ar: _D(name="PKG-OLD"),
             "portal_signed_signers": lambda name: calls.append(name) or ([], None)}
        exec(compile(_fns(_read("lifecycle.py"), ["_portal_before_lock"]), "l", "exec"), g)
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.permissions": perms,
                "ecentric_workspace.platform.esign.signing_files": sf}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            return g["_portal_before_lock"](BD, "CTR-1"), calls
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_chi_khi_can_bo_sung(self):
        r, calls = self._run("Pending")
        self.assertIsNone(r)
        self.assertEqual(calls, [])
        r, calls = self._run("Information Required")
        self.assertEqual(r, ("PKG-OLD", "DOC-1", [], None))
        self.assertEqual(calls, ["PKG-OLD"])


if __name__ == "__main__":
    unittest.main()
