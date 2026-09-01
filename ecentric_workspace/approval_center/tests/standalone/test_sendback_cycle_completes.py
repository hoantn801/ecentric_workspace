# Copyright (c) 2026, eCentric and contributors
"""Bi tra lai roi gui lai: chu trinh ky phai DI HET, khong duoc ket giua duong.

Ba lo hong xep chong nhau, phat hien 2026-08-29 khi ra soat ba kich ban Hoan yeu cau:

  1. `_signable_content_changed` so ma bam sha256 CUA MINH voi `File.content_hash` CUA
     FRAPPE. Frappe khong bao dam truong do la sha256. Neu khac thuat toan thi hai tap
     khong bao gio giao nhau -> ham luon tra "da doi" -> LAN GUI LAI NAO cung tao ban moi
     va bat moi nguoi ky lai, ke ca khi chi dinh kem them mot to hoa don.

  2. Duong GUI LAI khong goi `sign_on_submit`. Lan gui dau, Submitter chuan bi + khoa + ky
     mot mach, va panel nguoi de nghi da bo het nut bam vi chung la trang thai noi bo. Nen
     sau khi goi duoc tao ban moi: goi o Draft, khong nut nao, yeu cau ket cung.

  3. `_setup_editable` tra "already_submitted" ngay khi ton tai EC Approval Request. Chung
     tu dinh kem them sau khi bi tra lai LA tep can ky (_add_requester_pdf_files danh dau
     moi PDF private la requires_signature=1), nhung khong ai dat duoc o ky cho no nua.

Ba loi mot minh moi cai deu du lam ke ho; chong len nhau thi moi lan tra lai deu thanh ngo
cut. Test o day CHAY ham that (nap module bang stub frappe) thay vi grep chuoi.
"""
import io
import os
import sys
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


def _load(module_name, relpath, extra_globals):
    """Nap mot module esign voi frappe gia, KHONG cham sys.modules that."""
    src = io.open(os.path.join(_ROOT, *relpath), encoding="utf-8").read()
    mod = types.ModuleType(module_name)
    mod.__dict__.update(extra_globals)
    exec(compile(src, "/".join(relpath), "exec"), mod.__dict__)
    return mod


class _Frappe(object):
    """Chi du de chay ham dang do. Moi thu khong khai bao deu no to."""

    def __init__(self, files=None, contents=None, values=None):
        self._files = files or []
        self._contents = contents or {}
        self._values = values or {}
        self.db = self

    # --- frappe.get_all -----------------------------------------------------
    def get_all(self, doctype, filters=None, fields=None, **kw):
        if doctype != "File":
            raise AssertionError("khong mong doi truy van %s" % doctype)
        rows = []
        for f in self._files:
            if (filters or {}).get("is_private") and not f.get("is_private"):
                continue
            rows.append(dict(f))
        return rows

    # --- frappe.get_doc("File", name).get_content() --------------------------
    def get_doc(self, doctype, name):
        if doctype != "File":
            raise AssertionError("khong mong doi get_doc %s" % doctype)
        contents = self._contents
        if name not in contents:
            raise Exception("khong doc duoc tep")

        class _Doc(object):
            def get_content(self):
                return contents[name]
        return _Doc()

    # --- frappe.db.get_value -------------------------------------------------
    def get_value(self, doctype, name, field=None, **kw):
        return self._values.get((doctype, name, field))


def _lifecycle(frappe_stub):
    hashing = _load("_h", ("platform", "esign", "hashing.py"), {})
    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.hashing = hashing
    esign_pkg.events = types.SimpleNamespace(emit=lambda *a, **k: None)
    esign_pkg.package = types.SimpleNamespace(
        package_files=lambda n: [],
        # xem chu thich o test_reopen_keeps_signatures: byte tep di qua raw_file_bytes
        raw_file_bytes=lambda n: frappe_stub.get_doc("File", n).get_content())
    saved = {k: sys.modules.get(k) for k in
             ("frappe", "ecentric_workspace.platform.esign",
              "ecentric_workspace.platform.esign.hashing",
              "ecentric_workspace.platform.esign.events",
              "ecentric_workspace.platform.esign.package")}
    sys.modules["frappe"] = frappe_stub
    sys.modules["ecentric_workspace.platform.esign"] = esign_pkg
    sys.modules["ecentric_workspace.platform.esign.hashing"] = hashing
    sys.modules["ecentric_workspace.platform.esign.events"] = esign_pkg.events
    sys.modules["ecentric_workspace.platform.esign.package"] = esign_pkg.package
    try:
        frappe_stub._ = lambda s: s
        src = io.open(os.path.join(_ROOT, "platform", "esign", "lifecycle.py"),
                      encoding="utf-8").read()
        mod = types.ModuleType("_lifecycle")
        exec(compile(src, "lifecycle.py", "exec"), mod.__dict__)
        return mod, hashing
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v          # KHONG de lai module gia cho bo test khac


class TestContentComparisonUsesOneYardstick(unittest.TestCase):
    """Lo hong 1: dung sha256 cua chinh minh o CA HAI ve."""

    def setUp(self):
        self.pkg = types.SimpleNamespace(name="PKG-1", business_doctype="EC Payment Request",
                                         business_name="PR-1")

    def _run(self, files, contents, locked_from):
        stub = _Frappe(files=files, contents=contents)
        mod, hashing = _lifecycle(stub)
        mod.pkgsvc = types.SimpleNamespace(
            package_files=lambda n: [
                {"requires_signature": 1, "sha256": hashing.sha256_bytes(c)}
                for c in locked_from],
            # Ban de len nay CHE MAT `raw_file_bytes` cua ban gia o tren. Thieu no thi ma
            # nguon nem AttributeError va verdict ra "unreadable" - trong y het mot tep hong
            # tren dia, nen loi ban gia doi lot thanh loi nghiep vu.
            raw_file_bytes=lambda n: stub.get_doc("File", n).get_content())
        return mod._signable_content_verdict(self.pkg), hashing

    def test_khong_doi_gi_thi_bao_khong_doi(self):
        pdf = b"%PDF-1.4 to trinh"
        changed, _h = self._run(
            files=[{"name": "F1", "file_name": "to-trinh.pdf", "file_url": "/private/a.pdf",
                    "is_private": 1}],
            contents={"F1": pdf}, locked_from=[pdf])
        self.assertEqual(changed, "unchanged",
                         "khong doi gi ma bao doi -> lan gui lai nao cung bi chan")

    def test_dinh_kem_them_bang_chung_khong_tinh_la_doi(self):
        pdf, hoadon = b"%PDF-1.4 to trinh", b"%PDF-1.4 hoa don"
        changed, _h = self._run(
            files=[{"name": "F1", "file_name": "to-trinh.pdf", "is_private": 1},
                   {"name": "F2", "file_name": "hoa-don.pdf", "is_private": 1}],
            contents={"F1": pdf, "F2": hoadon}, locked_from=[pdf])
        self.assertEqual(changed, "unchanged",
                         "KICH BAN 1: bo sung chung tu -> di tiep, khong ky lai")

    def test_thay_noi_dung_to_trinh_thi_PHAI_bao_doi(self):
        cu, moi = b"%PDF-1.4 so tien 10", b"%PDF-1.4 so tien 999"
        changed, _h = self._run(
            files=[{"name": "F1", "file_name": "to-trinh.pdf", "is_private": 1}],
            contents={"F1": moi}, locked_from=[cu])
        self.assertEqual(changed, "changed",
                         "KICH BAN 2: sua to trinh da ky -> duong gui lai phai DUNG HAN")

    def test_go_mat_tep_da_ky_thi_bao_doi(self):
        pdf = b"%PDF-1.4 to trinh"
        changed, _h = self._run(files=[], contents={}, locked_from=[pdf])
        self.assertEqual(changed, "changed")

    def test_doc_hong_thi_coi_nhu_da_doi(self):
        pdf = b"%PDF-1.4 to trinh"
        changed, _h = self._run(
            files=[{"name": "F1", "file_name": "to-trinh.pdf", "is_private": 1}],
            contents={}, locked_from=[pdf])       # get_doc nem loi
        self.assertEqual(changed, "unreadable",
                         "khong doc duoc phai noi dung la khong doc duoc, khong noi 'da doi'")

    def test_khong_con_doc_content_hash_cua_frappe(self):
        # Bang chung truc tiep cho lo hong 1: truong do la cua framework, khong bao dam sha256.
        src = io.open(os.path.join(_ROOT, "platform", "esign", "lifecycle.py"),
                      encoding="utf-8").read()
        body = src.split("def _signable_content_verdict")[1].split("\ndef ")[0]
        self.assertNotIn('"content_hash"', body,
                         "so sha256 voi content_hash = do hai dai luong bang hai thuoc do")


class TestResubmitFinishesTheSigningCycle(unittest.TestCase):
    """Lo hong 2: gui lai phai chuan bi + khoa + ky nhu lan gui dau."""

    def _resubmitter_src(self):
        src = io.open(os.path.join(_ROOT, "approval_center", "shared", "finance_support.py"),
                      encoding="utf-8").read()
        return src.split("class Resubmitter")[1]

    def test_goi_sign_on_submit_khi_goi_ky_duoc_tao_ban_moi(self):
        body = self._resubmitter_src()
        self.assertIn("sign_on_submit", body,
                      "goi ky tao ban moi ma khong ai ky -> yeu cau ket cung")

    def test_chi_goi_khi_that_su_co_ban_moi(self):
        import ast
        src = io.open(os.path.join(_ROOT, "approval_center", "shared", "finance_support.py"),
                      encoding="utf-8").read()
        tree = ast.parse(src)
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            calls = [n for n in ast.walk(node)
                     if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "sign_on_submit"]
            if calls:
                found.append(ast.dump(node.test))
        self.assertTrue(found, "sign_on_submit phai nam trong mot nhanh dieu kien")
        self.assertTrue(any("revised" in t for t in found),
                        "chi ky lai khi goi THAT SU duoc tao ban moi, khong phai moi lan gui lai")


class TestPlacementReopensForARevisedDraft(unittest.TestCase):
    """Lo hong 3: co Approval Request khong con dong nghia 'cam sua vinh vien'."""

    def _setup_editable(self, ar, is_draft, req_status, needs_review=False):
        src = io.open(os.path.join(_ROOT, "platform", "esign", "document_setup.py"),
                      encoding="utf-8").read()
        start = src.index("def _setup_editable")
        end = src.index("def _assert_setup_editable")
        env = {
            "perms": types.SimpleNamespace(business_approval_request=lambda b, n: ar),
            "_current_package": lambda b, n: ("PKG-2", "Draft" if is_draft else "Locked",
                                              is_draft, needs_review),
            "frappe": types.SimpleNamespace(
                db=types.SimpleNamespace(get_value=lambda dt, nm, f: req_status)),
            "AR": "EC Approval Request",
        }
        exec(compile(src[start:end], "document_setup.py", "exec"), env)
        return env["_setup_editable"]("EC Payment Request", "PR-1")

    def test_chua_gui_thi_sua_duoc(self):
        self.assertEqual(self._setup_editable(None, True, None), (True, None))

    def test_goi_da_khoa_thi_khong_sua_duoc(self):
        ok, reason = self._setup_editable("AR-1", False, "Signed")
        self.assertFalse(ok)
        self.assertEqual(reason, "already_submitted")

    def test_goi_ban_moi_dang_cho_nguoi_de_nghi_ky_thi_MO_LAI(self):
        ok, reason = self._setup_editable("AR-1", True, "Pending")
        self.assertTrue(ok, "KICH BAN 3: chung tu bo sung la tep CAN KY, phai dat duoc o ky")
        self.assertIsNone(reason)

    def test_da_ky_roi_thi_dong_lai_ngay_ca_khi_con_draft(self):
        ok, reason = self._setup_editable("AR-1", True, "Signed")
        self.assertFalse(ok, "nguoi de nghi da ky -> khong duoc doi vi tri o ky nua")

    def test_cau_hinh_mo_ho_van_dong(self):
        ok, reason = self._setup_editable("AR-1", True, "Pending", needs_review=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "needs_review")

    def test_doc_hong_thi_dong_cua(self):
        src = io.open(os.path.join(_ROOT, "platform", "esign", "document_setup.py"),
                      encoding="utf-8").read()
        start = src.index("def _awaiting_requester_signature")
        end = src.index("def _assert_setup_editable")

        def _boom(*a, **k):
            raise Exception("db down")
        env = {"frappe": types.SimpleNamespace(db=types.SimpleNamespace(get_value=_boom)),
               "AR": "EC Approval Request",
               "_AWAITING_REQUESTER": ("Pending",)}
        exec(compile(src[start:end], "document_setup.py", "exec"), env)
        self.assertFalse(env["_awaiting_requester_signature"]("AR-1"),
                         "khong doc duoc trang thai -> khong duoc mo cua")


if __name__ == "__main__":
    unittest.main()
