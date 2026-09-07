# Copyright (c) 2026, eCentric and contributors
"""Chuyen nguoi xu ly (07/09) - nut Assign tren 5 form co fulfillment.

Bo test giu nam dieu, ca nam deu tung lam hong viec that:

  1. KHOA CHONG TROI phai khop nguon. Sua main_section.html ma quen bump BASELINE_SHA256
     thi upsert_web_page TU CHOI ghi, patch bao "unchanged", va ban sua khong bao gio len
     production - trong khi Patch Log van xanh. Test nay so sha256 that cua file voi hang
     BASELINE trong page_sync.py.
  2. Landmark cua p152 phai CO THAT trong nguon. Patch tu kiem landmark sau khi sync; neu
     landmark viet sai chinh ta thi deploy chet giua chung.
  3. Nut phai duoc noi day du: nut -> dispatcher -> ham. Thieu mot mat xich la nut chet.
  4. KHONG cho go email tu do. Nguoi nhan phai chon tu danh sach server tra ve, vi engine
     chi chap nhan Fulfiller cau hinh - go tay chi tao cai bay.
  5. Hoi lai khi quan tri nhan viec (`claim_is_admin_override`) - dung cai da lam Hoan bam
     nham ho so nghi viec 07/09.
"""
import ast
import hashlib
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "features")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
FORMS = ("asset_request", "data_request", "document_request", "resignation", "system_request")


def _html_path(f):
    return os.path.join(_ROOT, "approval_center", "features", f, "ui", "main_section.html")


def _sync_path(f):
    return os.path.join(_ROOT, "approval_center", "features", f, "infrastructure", "page_sync.py")


def _read(p):
    return io.open(p, encoding="utf-8").read()


class TestDriftLock(unittest.TestCase):
    def test_baseline_sha_khop_voi_nguon(self):
        for f in FORMS:
            src = _read(_html_path(f))
            real = hashlib.sha256(src.encode("utf-8")).hexdigest()
            sync = _read(_sync_path(f))
            m = re.search(r'BASELINE_SHA256 = "([0-9a-f]{64})"', sync)
            self.assertTrue(m, "%s: khong thay BASELINE_SHA256" % f)
            self.assertEqual(
                m.group(1), real,
                "%s: BASELINE_SHA256 khong khop main_section.html. Sua giao dien thi PHAI "
                "bump sha va day sha cu xuong SUPERSEDES_SHA256 trong CUNG commit, khong thi "
                "ban sua khong bao gio len production." % f)

    def test_sha_cu_duoc_giu_trong_supersedes(self):
        """Luc deploy, live van dang giu bytes CU -> phai con trong danh sach chap nhan."""
        for f in FORMS:
            sync = _read(_sync_path(f))
            block = re.search(r"SUPERSEDES_SHA256 = \((.*?)\)", sync, re.S)
            self.assertTrue(block, "%s: khong thay SUPERSEDES_SHA256" % f)
            self.assertGreaterEqual(
                len(re.findall(r'"[0-9a-f]{64}"', block.group(1))), 1,
                "%s: SUPERSEDES rong" % f)


class TestPatchLandmarks(unittest.TestCase):
    def test_landmark_p152_co_that_trong_nguon(self):
        patch = _read(os.path.join(_ROOT, "approval_center", "patches",
                                   "p152_resync_five_forms_reassign.py"))
        # Doc bang CAY CU PHAP, khong regex: landmark chua dau ngoac ("doReassign(name)")
        # nen moi regex cat theo ")" deu cat nham va cho ra danh sach RONG -> test xanh gia.
        landmarks = None
        for node in ast.walk(ast.parse(patch)):
            if (isinstance(node, ast.Assign) and node.targets
                    and getattr(node.targets[0], "id", None) == "_LANDMARKS"):
                landmarks = list(ast.literal_eval(node.value))
        self.assertTrue(landmarks, "khong doc duoc _LANDMARKS tu p152")
        for f in FORMS:
            src = _read(_html_path(f))
            for L in landmarks:
                self.assertIn(L, src, "%s: nguon thieu landmark %r ma p152 se kiem" % (f, L))

    def test_p152_da_dang_ky(self):
        txt = _read(os.path.join(_ROOT, "patches.txt"))
        self.assertIn("patches.p152_resync_five_forms_reassign", txt)


class TestUiWiring(unittest.TestCase):
    def test_nut_dispatcher_va_ham_du_ca_ba(self):
        for f in FORMS:
            src = _read(_html_path(f))
            self.assertIn('data-act="reassign"', src, "%s: thieu nut" % f)
            self.assertIn('if(a==="reassign") return doReassign(name);', src,
                          "%s: nut co ma dispatcher khong goi -> nut chet" % f)
            self.assertIn("function doReassign(name)", src, "%s: thieu ham" % f)
            self.assertIn("cap.can_reassign", src, "%s: nut khong gate bang quyen" % f)

    def test_goi_dung_hai_endpoint(self):
        for f in FORMS:
            src = _read(_html_path(f))
            self.assertIn('call("list_reassign_targets"', src, "%s" % f)
            self.assertIn('call("reassign_fulfillment"', src, "%s" % f)

    def test_khong_cho_go_email_tu_do(self):
        """Nguoi nhan phai den TU danh sach server; mot o input tu do se de nguoi dung go
        email ma engine tu choi ngay sau do."""
        for f in FORMS:
            src = _read(_html_path(f))
            body = src[src.index("function doReassign(name)"):]
            body = body[:body.index("function _claim(")]
            self.assertIn('<select id="m-newowner">', body, "%s: phai la select" % f)
            self.assertNotIn('id="m-newowner" type="text"', body, "%s" % f)

    def test_hoi_lai_khi_quan_tri_nhan_viec(self):
        for f in FORMS:
            src = _read(_html_path(f))
            self.assertIn("cap.claim_is_admin_override", src, "%s: thieu chot hoi lai" % f)
            body = src[src.index("function doClaim(name)"):]
            body = body[:body.index("function _claim(")]
            self.assertIn("modal(", body,
                          "%s: co co ma khong hien hop xac nhan" % f)


class TestBackendWiring(unittest.TestCase):
    def _read_shared(self, *parts):
        return _read(os.path.join(_ROOT, "approval_center", "shared", *parts))

    def test_endpoint_duoc_whitelist_va_reassign_la_post(self):
        src = self._read_shared("fulfillment_api_adapter.py")
        self.assertIn("def list_reassign_targets(name)", src)
        self.assertIn("def reassign_fulfillment(name, new_user)", src)
        m = re.search(r"(@frappe\.whitelist\([^)]*\)\s*\n\s*def reassign_fulfillment)", src)
        self.assertTrue(m)
        self.assertIn('methods=["POST"]', m.group(1),
                      "reassign_fulfillment doi trang thai -> phai POST, khong duoc GET")

    def test_service_uy_quyen_cho_engine_khong_tu_che_luat(self):
        src = self._read_shared("requests", "fulfillment_service.py")
        self.assertIn("transitions.reassign_fulfillment", src)
        body = src[src.index("def reassign(definition, name, new_user)"):]
        self.assertNotIn("set_value", body,
                         "khong duoc ghi thang; engine phai lo ToDo + audit")

    def test_capabilities_co_ca_hai_co(self):
        src = self._read_shared("requests", "capabilities.py")
        self.assertIn('"can_reassign":', src)
        self.assertIn('"claim_is_admin_override":', src)


class TestSelfMaintainingDriftLock(unittest.TestCase):
    """p152 refused ca 5 trang trong lan deploy dau (07/09).

    Ly do KHONG phai live bi sua tay: live khop TUNG BYTE voi nguon tren main. Ly do la
    hang `BASELINE_SHA256` trong page_sync.py da lac hau so voi chinh file main_section.html
    cua no tu truoc - nen khi bump, thu bi day xuong SUPERSEDES la mot HANG DA CU, khong
    phai sha cua noi dung file truoc do. Ket qua: live khong khop bat ky gia tri nao ->
    upsert tu choi ghi -> patch raise -> chet ca lan migrate.

    Cach chua goc: `record_live_sha` - ghi lai sha live SAU khi may chu xu ly, de lan sau
    upsert nhan ra chinh ban ghi cua minh va khong can ai chep sha bang tay nua.
    payment_request da lam tu p056; nam form con lai thi khong. Test nay bat buoc MOI trang
    co drift lock deu phai tu bao tri.
    """

    def _feature_sync_files(self):
        base = os.path.join(_ROOT, "approval_center", "features")
        out = []
        for feat in sorted(os.listdir(base)):
            p = os.path.join(base, feat, "infrastructure", "page_sync.py")
            if os.path.isfile(p):
                out.append((feat, p))
        return out

    #: Tran so trang CO khoa chong troi ma KHONG tu ghi lai sha. Da dua ve 0 (07/09):
    #: moi trang deu tu bao tri. Tran nay chi duoc PHEP GIU 0.
    MAX_CHUA_SUA = 0

    def test_p153_gieo_sha_da_dang_ky(self):
        txt = _read(os.path.join(_ROOT, "patches.txt"))
        self.assertIn("patches.p153_seed_page_sync_sha", txt)

    def test_p153_khong_bao_gio_nem_loi(self):
        """Patch chay trong migrate; mot exception thoat ra la chet ca lan deploy (p116)."""
        src = _read(os.path.join(_ROOT, "approval_center", "patches",
                                 "p153_seed_page_sync_sha.py"))
        tree = ast.parse(src)
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execute"]
        self.assertTrue(fn, "khong thay execute()")
        self.assertFalse([n for n in ast.walk(fn[0]) if isinstance(n, ast.Raise)],
                         "p153 khong duoc raise")
        self.assertTrue([n for n in ast.walk(fn[0]) if isinstance(n, ast.Try)],
                        "vong lap phai boc try/except de mot trang loi khong chan trang khac")

    def test_p153_chi_ghi_van_tay_khong_ghi_noi_dung(self):
        """Gieo sha la thao tac AN TOAN vi no khong dong vao noi dung trang. Neu ai do them
        upsert_web_page vao day thi patch bien thanh mot lan ghi de 26 trang."""
        src = _read(os.path.join(_ROOT, "approval_center", "patches",
                                 "p153_seed_page_sync_sha.py"))
        called = {n.func.attr for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("record_live_sha", called)
        self.assertNotIn("upsert_web_page", called)
        self.assertNotIn("sync", called)

    def test_khong_them_trang_moi_thieu_record_live_sha(self):
        """Tran chi duoc DI XUONG. Trang moi ma thieu record_live_sha se lam vo tran nay
        truoc khi no kip lam chet mot lan deploy."""
        thieu = [feat for feat, path in self._feature_sync_files()
                 if "expect_sha" in _read(path) and "record_live_sha" not in _read(path)]
        self.assertLessEqual(
            len(thieu), self.MAX_CHUA_SUA,
            "co them trang co khoa chong troi ma khong tu ghi sha: %s" % thieu)


if __name__ == "__main__":
    unittest.main(verbosity=2)
