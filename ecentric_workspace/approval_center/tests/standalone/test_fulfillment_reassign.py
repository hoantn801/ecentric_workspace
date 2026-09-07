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


if __name__ == "__main__":
    unittest.main(verbosity=2)
