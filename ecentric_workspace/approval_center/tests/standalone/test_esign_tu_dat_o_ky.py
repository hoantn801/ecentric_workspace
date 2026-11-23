# Copyright (c) 2026, eCentric and contributors
"""Tu dat o ky theo moc [[KY_BEN_A]] / [[KY_BEN_B]] + doi chieu noi dung tep (18/11/2026, chot giua
chat Hop dong va chat Ky so - THIETKE_ky_so_hop_dong muc 2e).

  1. pdf_markers.analyze: moc chu trang 1pt bi cat nhieu manh tren cung dong -> van nhan; toa do
     he chuan (goc tren-trai, point, trang tu 1); moc tren 2 dong -> khong nhan; trang xoay -> bo +
     ly do; PDF khong lop chu -> has_text_layer False; o ky 180x60 NGAY TREN moc, trong trang.
  2. document_verification: khong khai hook -> not_required; khong lop chu -> VAN goi ham voi
     pages_text rong (PR-G 23/11) - ham tra no_text thi chan, not_applicable thi qua (KHONG goi
     ham); ham tra match / mismatch / la / nem loi; cache theo sha; package_errors.
  3. placement_service.auto_place: di qua save_placement; chan khi khong khop / khong lop chu;
     khong moc -> bao keo tay; KY_BEN_A -> slot ky duy nhat; KY_BEN_B chua co slot -> bo qua;
     slot da co o -> khong ghi de.
  4. preflight khoa goi goi doi chieu; api POST.
PDF test dung tay (khong can reportlab).
"""
import io
import os
import sys
import types
import unittest
import zlib

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


def _exec(name, mods=None):
    mods = mods or {}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_m_" + name.replace(".", "_"))
        m.__file__ = os.path.join(_ESIGN, name)
        exec(compile(_read(name), name, "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m


# --------------------------------------------------------------------------- PDF dung tay
def make_pdf(streams, rotate=0, width=595.28, height=841.89):
    """PDF toi gian: moi trang mot luong lenh ve chu (font Helvetica)."""
    objs = []
    page_ids = []
    font_id = 3
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(None)                                   # 2: Pages (dien sau)
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for s in streams:
        data = zlib.compress(s.encode("latin-1"))
        objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data
                    + b"\nendstream")
        cid = len(objs)
        rot = (" /Rotate %d" % rotate) if rotate else ""
        objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f]%s "
                     "/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                     % (width, height, rot, font_id, cid)).encode())
        page_ids.append(len(objs))
    objs[1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
               % (" ".join("%d 0 R" % i for i in page_ids), len(page_ids))).encode()
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    x = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for o in offs:
        out.write(b"%010d 00000 n \n" % o)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objs) + 1, x))
    return out.getvalue()


BODY = ("BT /F1 11 Tf 72 780 Td (HOP DONG DICH VU SO 01102026/HDDV tong tien 29.700.000) Tj ET\n"
        "BT /F1 11 Tf 72 500 Td (DAI DIEN BEN A                DAI DIEN BEN B) Tj ET\n")
WHITE = "1 1 1 rg\n"
MARK_SPLIT = "BT /F1 1 Tf 80 460 Td ([[KY_) Tj (BEN_A]]) Tj ET\n"
MARK_B = "BT /F1 1 Tf 360 460 Td ([[KY_BEN_B]]) Tj ET\n"


def _pm():
    return _exec("pdf_markers.py")


class TestMarkers(unittest.TestCase):
    def test_moc_bi_cat_manh_van_nhan_toa_do_chuan(self):
        r = _pm().analyze(make_pdf([BODY + WHITE + MARK_SPLIT + MARK_B]))
        self.assertTrue(r["has_text_layer"])
        got = {m["name"]: (m["page_index"], round(m["x"]), round(m["y"], 1)) for m in r["markers"]}
        self.assertEqual(got["KY_BEN_A"], (1, 80, round(841.89 - 460, 1)))
        self.assertEqual(got["KY_BEN_B"][0:2], (1, 360))
        self.assertIn("29.700.000", r["pages_text"][0])

    def test_moc_tren_hai_dong_thi_khong(self):
        s = BODY + "BT /F1 1 Tf 80 460 Td ([[KY_) Tj ET\nBT /F1 1 Tf 80 440 Td (BEN_A]]) Tj ET\n"
        self.assertEqual(_pm().analyze(make_pdf([s]))["markers"], [])

    def test_trang_xoay_bo_qua_co_ly_do(self):
        r = _pm().analyze(make_pdf([BODY + MARK_SPLIT], rotate=90))
        self.assertEqual(r["markers"], [])
        self.assertEqual(r["skipped"][0]["reason"], "rotated_page:90")

    def test_khong_lop_chu(self):
        r = _pm().analyze(make_pdf(["0 0 1 rg 50 50 200 200 re f\n"]))
        self.assertFalse(r["has_text_layer"])
        self.assertEqual(r["markers"], [])

    def test_pdf_hong(self):
        r = _pm().analyze(b"not a pdf")
        self.assertFalse(r["ok"])
        self.assertFalse(r["has_text_layer"])

    def test_dau_cach_chen_vao_moc_van_nhan(self):
        for mk in ("BT /F1 1 Tf 80 460 Td ([) Tj 5 0 Td ([KY_BEN_A]]) Tj ET\n",
                   "BT /F1 1 Tf 80 460 Td ([[KY_) Tj ET\nBT /F1 1 Tf 90 460.6 Td (BEN_A]]) Tj ET\n"):
            r = _pm().analyze(make_pdf([BODY + mk]))
            self.assertEqual([m["name"] for m in r["markers"]], ["KY_BEN_A"], mk)

    def test_moc_sau_chu_khac_cung_khoi_thi_khong_tin_toa_do(self):
        s = BODY + "BT /F1 11 Tf 80 460 Td (Dai dien ben A: ) Tj /F1 1 Tf ([[KY_BEN_A]]) Tj ET\n"
        r = _pm().analyze(make_pdf([s]))
        self.assertEqual(r["markers"], [])
        self.assertEqual(r["skipped"][0]["reason"], "position_unreliable")

    def test_moc_giua_manh_chu_khac_thi_khong_tin(self):
        s = BODY + "BT /F1 11 Tf 80 460 Td (Dai dien ben A [[KY_BEN_A]]) Tj ET\n"
        r = _pm().analyze(make_pdf([s]))
        self.assertEqual(r["markers"], [])
        self.assertEqual(r["skipped"][0]["reason"], "position_unreliable")

    def test_chu_xoay_khong_lam_moc(self):
        s = BODY + "BT /F1 1 Tf 0 1 -1 0 80 460 Tm ([[KY_BEN_A]]) Tj ET\n"
        self.assertEqual(_pm().analyze(make_pdf([s]))["markers"], [])

    def test_ban_scan_kem_moc_khong_tinh_la_co_lop_chu(self):
        r = _pm().analyze(make_pdf(["0 0 1 rg 50 50 200 200 re f\n" + MARK_SPLIT + MARK_B]))
        self.assertFalse(r["has_text_layer"])

    def test_co_chu_that_theo_ma_tran(self):
        s = BODY + "BT /F1 1 Tf 11 0 0 11 80 460 Tm ([[KY_BEN_A]]) Tj ET\n"
        r = _pm().analyze(make_pdf([s]))
        self.assertAlmostEqual(r["markers"][0]["font_size"], 11.0, places=1)

    def test_cropbox_lech_goc(self):
        pdf = make_pdf([BODY + MARK_B]).replace(
            b"/MediaBox [0 0 595.28 841.89]", b"/MediaBox [0 0 595.28 841.89] /CropBox [50 40 545 801]")
        r = _pm().analyze(pdf)
        m = r["markers"][0]
        self.assertEqual((round(m["x"]), round(m["y"], 1)), (310, round(801 - 460, 1)))

    def test_trang_thu_hai(self):
        r = _pm().analyze(make_pdf([BODY, BODY + MARK_B]))
        self.assertEqual([(m["name"], m["page_index"]) for m in r["markers"]], [("KY_BEN_B", 2)])

    def test_o_ky_ngay_tren_moc_va_trong_trang(self):
        pm = _pm()
        b = pm.box_for({"page_index": 1, "x": 80, "y": 381.89, "font_size": 1,
                        "page_width": 595.28, "page_height": 841.89})
        self.assertEqual((b["width"], b["height"]), (180.0, 60.0))
        self.assertAlmostEqual(b["y"] + b["height"], 381.89 - 1 - 2, places=1)
        self.assertEqual(b["x"], 80)
        b = pm.box_for({"page_index": 1, "x": 560, "y": 20, "font_size": 1,
                        "page_width": 595.28, "page_height": 841.89})
        self.assertLessEqual(b["x"] + b["width"], 595.28)
        self.assertGreaterEqual(b["y"], 0)


# --------------------------------------------------------------------------- doi chieu
class _Cache(object):
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v


def _dv(hook=None, fn=None):
    fk = types.ModuleType("frappe")
    cache = _Cache()
    fk.cache = lambda: cache
    fk.get_hooks = lambda name: ({"EC Contract Review Request": [hook]} if hook else {})
    fk.get_attr = lambda path: fn
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk._mod = ["2026-11-22 01:00"]
    fk.db = types.SimpleNamespace(get_value=lambda dt, n, f=None, **k: fk._mod[0])
    hs = types.ModuleType("hashing")
    import hashlib
    hs.sha256_bytes = lambda b: hashlib.sha256(b).hexdigest()
    pkgroot = types.ModuleType("ecentric_workspace.platform.esign")
    pkgroot.hashing = hs
    pkgroot.pdf_markers = _pm()
    m = _exec("document_verification.py", {"frappe": fk,
                                           "ecentric_workspace.platform.esign": pkgroot,
                                           "ecentric_workspace.platform.esign.hashing": hs,
                                           "ecentric_workspace.platform.esign.pdf_markers":
                                               pkgroot.pdf_markers})
    m._cache = cache
    m._fk = fk
    return m


PDF_OK = make_pdf([BODY + WHITE + MARK_SPLIT + MARK_B])
PDF_SCAN = make_pdf(["0 0 1 rg 50 50 200 200 re f\n"])
BD = "EC Contract Review Request"


class TestVerify(unittest.TestCase):
    def test_khong_khai_hook(self):
        r = _dv().verify("EC Payment Request", "PR-1", "a.pdf", PDF_OK)
        self.assertEqual(r["status"], "not_required")

    def test_khong_lop_chu_van_goi_ham_voi_trang_rong(self):
        """PR-G 23/11: nghiep vu quyet (KOL bat buoc lop chu -> no_text; ban scan WF05 ->
        not_applicable). Ham tra no_text khong kem ly do -> cau mac dinh 'Luu thanh PDF'."""
        calls = []
        m = _dv("x.y", lambda *a: calls.append(a) or {"status": "no_text"})
        r = m.verify(BD, "CTR-1", "a.pdf", PDF_SCAN)
        self.assertEqual(r["status"], "no_text")
        self.assertIn("Lưu thành PDF", r["reason"])
        self.assertFalse(r["has_text_layer"])
        self.assertEqual(calls, [(BD, "CTR-1", "a.pdf", [])])

    def test_match_mismatch_la_loi(self):
        seen = []
        m = _dv("x.y", lambda bd, bn, fn, pages: seen.append((bd, bn, fn, pages))
                or {"status": "match"})
        self.assertEqual(m.verify(BD, "CTR-1", "a.pdf", PDF_OK)["status"], "match")
        self.assertIn("29.700.000", seen[0][3][0], "ham nhan chu tung trang")
        m = _dv("x.y", lambda *a: {"status": "mismatch", "reason": "Sai so tien"})
        r = m.verify(BD, "CTR-1", "a.pdf", PDF_OK)
        self.assertEqual((r["status"], r["reason"]), ("mismatch", "Sai so tien"))
        m = _dv("x.y", lambda *a: {"status": "ok"})
        self.assertEqual(m.verify(BD, "CTR-1", "a.pdf", PDF_OK)["status"], "error")

        def boom(*a):
            raise RuntimeError("x")
        m = _dv("x.y", boom)
        r = m.verify(BD, "CTR-1", "a.pdf", PDF_OK)
        self.assertEqual(r["status"], "error")
        self.assertTrue(all(k.endswith(":err") for k in m._cache.d), "loi chi cache ngan (:err)")

    def test_cache_theo_sha(self):
        n = []
        m = _dv("x.y", lambda *a: n.append(1) or {"status": "match"})
        m.verify(BD, "CTR-1", "a.pdf", PDF_OK)
        m.verify(BD, "CTR-1", "a.pdf", PDF_OK)
        self.assertEqual(len(n), 1)
        m.verify(BD, "CTR-1", "a.pdf", PDF_OK + b" ")
        self.assertEqual(len(n), 2, "tep doi -> doi chieu lai")
        m._fk._mod[0] = "2026-11-22 02:00"
        m.verify(BD, "CTR-1", "a.pdf", PDF_OK)
        self.assertEqual(len(n), 3, "phieu sua -> doi chieu lai")

    def test_package_errors_trung_cache_khong_doc_tep(self):
        import hashlib
        m = _dv("x.y", lambda *a: {"status": "match"})
        sha = hashlib.sha256(PDF_OK).hexdigest()
        m.verify(BD, "CTR-1", "a.pdf", PDF_OK)
        f = types.SimpleNamespace(name="DSF-1", file_name="a.pdf", sha256=sha)
        self.assertEqual(m.package_errors("P", BD, "CTR-1", [f], lambda x: 1 / 0), [])

    def test_package_errors(self):
        f = types.SimpleNamespace(name="DSF-1", file_name="a.pdf")
        m = _dv("x.y", lambda *a: {"status": "mismatch"})
        self.assertEqual(m.package_errors("P", BD, "CTR-1", [f], lambda x: PDF_OK),
                         ["document_verify:a.pdf:mismatch"])
        m = _dv()
        self.assertEqual(m.package_errors("P", "EC Payment Request", "PR", [f],
                                          lambda x: 1 / 0), [])


# --------------------------------------------------------------------------- auto_place
class _D(dict):
    __getattr__ = dict.get


def _ps(content, required, verify_status=None, placements=(), save_fail=None, hook=None):
    w = {"saved": [], "content": content}
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.get_hooks = lambda name: ({BD: [hook[0]]} if hook else {})
    fk.get_attr = lambda p: hook[1]
    fk.throw = lambda m, *a, **k: (_ for _ in ()).throw(RuntimeError(m))
    ds = types.ModuleType("ds")
    ds._is_pdf_name = lambda n, u=None: str(n or "").lower().endswith(".pdf")
    pk = types.ModuleType("pk")
    pk.raw_file_bytes = lambda fid: w["content"]
    import hashlib as _hl
    pk.hashing = types.SimpleNamespace(sha256_bytes=lambda b: _hl.sha256(b).hexdigest())
    pm_ = types.ModuleType("perms")
    sp = types.ModuleType("sp")
    dv = types.ModuleType("dv")
    dv.verifier_path = lambda bd: "x.y" if verify_status else None
    dv.verify = lambda bd, bn, fn, c, a=None, sha=None: {"status": verify_status, "reason": "ly do"}
    dv.PASS_STATUSES = ("match", "not_applicable")
    sf = types.ModuleType("signing_files")           # PR-G: loai phieu khong khai tep ky
    sf.is_signing_file = lambda *a, **k: None
    sf.reconcile_draft = lambda pkg, bd, bn: []          # PR-G vong 2: khong khai -> khong go gi
    lc = types.ModuleType("lifecycle")
    lc.maybe_reopen_for_edit = lambda bd, bn, portal=None: w["order"].append("reopen?") and None
    lc.portal_for_possible_reopen = lambda bd, bn: w["order"].append("portal") or None
    lc.locked_signable_shas = lambda bd, bn: None      # khong "Can bo sung" -> khong mo lai
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.document_setup, root.package, root.permissions, root.signer_plan = ds, pk, pm_, sp
    root.document_verification, root.pdf_markers = dv, _pm()
    root.signing_files, root.lifecycle = sf, lc
    m = _exec("placement_service.py", {
        "frappe": fk, "ecentric_workspace.platform.esign": root,
        "ecentric_workspace.platform.esign.document_setup": ds,
        "ecentric_workspace.platform.esign.package": pk,
        "ecentric_workspace.platform.esign.permissions": pm_,
        "ecentric_workspace.platform.esign.signer_plan": sp,
        "ecentric_workspace.platform.esign.document_verification": dv,
        "ecentric_workspace.platform.esign.signing_files": sf,
        "ecentric_workspace.platform.esign.pdf_markers": root.pdf_markers})
    w["order"] = []
    ds._assert_can_classify = lambda bd, bn: w["order"].append("perm")   # PR-G vong 2 M-1
    m._assert_write_ok = lambda bd, bn: w["order"].append("gate") or "PKG-D"

    def gv(*a, **k):
        w.setdefault("locks", []).append(k.get("for_update"))
        w["order"].append("lock")
    fk.db = types.SimpleNamespace(get_value=gv, rollback=lambda: w["order"].append("rollback"))
    m._resolve_file = lambda bd, bn, ref: _D(name=ref, file_name="hd.pdf", file_url="/x/hd.pdf")
    m._required_slots = lambda bd, bn: (required, {s["slot_key"] for s in required}, {})
    m.placement_state = lambda bd, bn, ref: {"placements": [dict(p) for p in placements]
                                             + [dict(signer_slot_key=s["box"]["signer_slot_key"])
                                                for s in w["saved"]]}

    def save(bd, bn, ref, box):
        w["saved"].append({"ref": ref, "box": box})
        return {"ok": False, "reason": save_fail} if save_fail else {"ok": True}
    m.save_placement = save
    real_mods = {"ecentric_workspace.platform.esign": root,
                 "ecentric_workspace.platform.esign.lifecycle": lc,
                 "ecentric_workspace.platform.esign.document_verification": dv,
                 "ecentric_workspace.platform.esign.pdf_markers": root.pdf_markers}

    def run():
        saved = {k: sys.modules.get(k) for k in real_mods}
        sys.modules.update(real_mods)
        try:
            return m.auto_place(BD, "CTR-1", "FILE-1")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
    return m, w, run


CEO = {"slot_key": "level:4", "kind": "approval_level", "required": True}
REQ = {"slot_key": "requester", "kind": "requester", "required": True}


class TestAutoPlace(unittest.TestCase):
    def test_dat_ben_a_vao_slot_ky_duy_nhat_bo_qua_ben_b(self):
        m, w, run = _ps(PDF_OK, [REQ, CEO], verify_status="match")
        r = run()
        self.assertTrue(r["ok"])
        self.assertEqual([(p["name"], p["slot"]) for p in r["placed"]], [("KY_BEN_A", "level:4")])
        self.assertEqual(w["saved"][0]["box"]["signer_slot_key"], "level:4")
        self.assertEqual(w["saved"][0]["box"]["width"], 180.0)
        self.assertIn({"name": "KY_BEN_B", "page_index": 1, "reason": "no_slot_for_marker"},
                      r["skipped"])
        self.assertEqual(w["locks"], [True], "khoa hang phieu truoc khi tinh o da co")
        # PR-G (QC vong 1): chi mo lai khi "Can bo sung" va SAU moi phep kiem tep - o day khong
        # phai truong hop do nen khong mo lai; van khoa truoc, chot ghi sau.
        self.assertEqual(w["order"][:6], ["perm", "portal", "rollback", "lock", "perm", "gate"],
                         "quyen -> doc cong (truoc khoa, QC PR-G vong 3) -> bo snapshot -> khoa "
                         "-> kiem lai quyen -> chot ghi")
        self.assertNotIn("reopen?", w["order"])

    def test_khong_khop_thi_chan_khong_dat(self):
        for st in ("mismatch", "no_text", "error"):
            m, w, run = _ps(PDF_OK, [CEO], verify_status=st)
            r = run()
            self.assertFalse(r["ok"], st)
            self.assertEqual(r["reason"], "verify_%s" % st)
            self.assertEqual(w["saved"], [])

    def test_khong_moc_thi_bao_keo_tay(self):
        m, w, run = _ps(make_pdf([BODY]), [CEO], verify_status="match")
        r = run()
        self.assertEqual(r["reason"], "no_markers")
        self.assertEqual(w["saved"], [])

    def test_khong_ghi_de_slot_da_co(self):
        m, w, run = _ps(PDF_OK, [CEO], verify_status="match",
                        placements=[{"signer_slot_key": "level:4"}])
        r = run()
        self.assertEqual(w["saved"], [])
        self.assertEqual(r["skipped"][0]["reason"], "already_placed")

    def test_nhieu_slot_ky_thi_khong_doan(self):
        m, w, run = _ps(PDF_OK, [CEO, dict(CEO, slot_key="level:3")], verify_status="match")
        r = run()
        self.assertEqual(w["saved"], [])

    def test_hook_gan_ca_ben_b(self):
        m, w, run = _ps(PDF_OK, [CEO, {"slot_key": "partner", "kind": "partner",
                                       "required": True}], verify_status="match",
                        hook=("h.k", lambda bd, bn, req: {"KY_BEN_A": "level:4",
                                                          "KY_BEN_B": "partner"}))
        r = run()
        self.assertEqual(sorted(p["slot"] for p in r["placed"]), ["level:4", "partner"])

    def test_save_bi_tu_choi_thi_bao(self):
        m, w, run = _ps(PDF_OK, [CEO], verify_status="match", save_fail="invalid_slot_key")
        r = run()
        self.assertEqual(r["placed"], [])
        self.assertIn("invalid_slot_key", [s["reason"] for s in r["skipped"]])

    def test_loai_phieu_khong_doi_chieu_van_dat(self):
        m, w, run = _ps(PDF_OK, [CEO], verify_status=None)
        r = run()
        self.assertEqual(len(r["placed"]), 1)


class TestWiring(unittest.TestCase):
    def test_preflight_goi_doi_chieu_chi_goi_draft(self):
        src = _read("package.py")
        i = src.index("def preflight_for_lock(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn("dv.package_errors(", body)
        self.assertIn('"business_doctype", "business_name"', body)
        self.assertIn('getattr(pkg, "status", None) == "Draft"', body)

    def test_gui_lai_tep_khong_doi_van_doi_chieu(self):
        src = _read("lifecycle.py")
        i = src.index("def on_request_reopened(")
        body = src[i:src.index("\ndef ", i + 10)]
        a = body.index('if verdict == "unchanged":')
        self.assertIn("_assert_documents_still_match(pkg)", body[a:a + 600])

    def test_cau_bao_tieng_viet(self):
        src = _read("requester.py")
        i = src.index("def _preflight_vi(")
        body = src[i:src.index("\ndef ", i + 10)]
        g = {}
        exec(compile(body, "x", "exec"), {"_PREFLIGHT_VI": {}}, g)
        f = g["_preflight_vi"]
        self.assertIn("không khớp phiếu", f("document_verify:hd.pdf:mismatch"))
        self.assertIn("Lưu thành PDF", f("document_verify:hd.pdf:no_text"))
        self.assertIn("chưa đối chiếu được", f("document_verify:hd.pdf:error"))

    def test_api_post(self):
        src = _read("api.py")
        i = src.index("def auto_place_signature_boxes(")
        self.assertIn('@frappe.whitelist(methods=["POST"])', src[i - 60:i])

    def test_auto_place_di_qua_save_placement(self):
        src = _read("placement_service.py")
        i = src.index("def auto_place(")
        body = src[i:]
        self.assertIn("save_placement(business_doctype, business_name, document_ref, box)", body)
        self.assertIn("_assert_write_ok(business_doctype, business_name)", body)


if __name__ == "__main__":
    unittest.main()
