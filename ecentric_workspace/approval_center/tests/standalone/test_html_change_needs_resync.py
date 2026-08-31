# Copyright (c) 2026, eCentric and contributors
"""An injected .html change shipped without a resync patch never reaches anyone.

document_signing_section.html and requester_signing_panel.html are not served from disk -
page_sync INJECTS them into a Web Page record. Changing the file in git and deploying does
nothing on its own: the site keeps serving the markup already stored in that record.

2026-08-29: the `_clampBox` drag fix shipped without a patch. Tests green, deploy clean, and
the same bug was reported within the hour - the browser was still running the old code. The
fix was real; it just never arrived. Second time this week.

A test cannot know which release a patch belongs to, so it pins the standing invariants:
every patch file is declared, nothing is declared twice, the page has a resync patch at all,
and each landmark that only exists in a NEW template version is matched by a patch that
mentions it. The last one is what would have caught the clamp release.
"""
import ast
import glob
import hashlib
import io
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _patches():
    return {os.path.basename(p): io.open(p, encoding="utf-8").read()
            for p in glob.glob(os.path.join(_ROOT, "approval_center", "patches", "p*.py"))}


def _ui(name):
    return io.open(os.path.join(_ROOT, "platform", "esign", "ui", name),
                   encoding="utf-8").read()


class TestPatchesAreDeclaredAndUnique(unittest.TestCase):
    def setUp(self):
        self.patches = _patches()
        self.assertTrue(self.patches, "khong doc duoc patch nao - phep kiem nay dang mu")
        self.listed = io.open(os.path.join(_ROOT, "patches.txt"), encoding="utf-8").read()

    def test_every_patch_file_is_declared(self):
        missing = [n[:-3] for n in self.patches if n[:-3] not in self.listed]
        self.assertEqual(missing, [],
                         "co file patch nhung khong khai trong patches.txt -> "
                         "bench migrate khong chay: %s" % missing)

    def test_nothing_is_declared_twice(self):
        lines = [x.strip() for x in self.listed.splitlines()
                 if x.strip() and not x.strip().startswith("[")]
        dupes = {x for x in lines if lines.count(x) > 1}
        self.assertEqual(dupes, set(), "dong trung trong patches.txt: %s" % dupes)

    def test_the_page_has_a_resync_patch_at_all(self):
        callers = [n for n, s in self.patches.items()
                   if "page_sync.sync()" in s and "payment_request" in s]
        self.assertTrue(callers,
                        "khong patch nao dong bo trang -> moi sua doi HTML deu vo ich")


class TestEachTemplateLandmarkHasAPatchThatMentionsIt(unittest.TestCase):
    """Cai da bat duoc lan 29/08 neu no ton tai luc do.

    Moi lan sua HTML, them mot dau moc o day cung voi tu khoa cua patch di kem. Neu ai do
    sua template ma quen patch, dau moc co trong file nhung khong patch nao nhac toi no.
    """

    #: dau moc trong template  ->  tu khoa phai xuat hien trong ten HOAC noi dung mot patch
    LANDMARKS = [
        ("document_signing_section.html", "Math.max(0, W - w)", "clamp"),
        ("document_signing_section.html", "ecdPager", "viewer_pages"),
        ("document_signing_section.html", "overflow:auto;min-width:0", "viewer_pages"),
        ("document_signing_section.html", "function _fitSig", "signature_fit"),
        ("document_signing_section.html", "STATE.can_add_supporting", "supporting_upload"),
        ("document_signing_section.html", "data-remove=", "remove_supporting"),
        ("requester_signing_panel.html", "requester_signature_processing", "processing_state"),
    ]

    def test_every_landmark_is_covered(self):
        patches = _patches()
        blob = "\n".join(list(patches) + list(patches.values()))
        for fname, landmark, keyword in self.LANDMARKS:
            with self.subTest(landmark=landmark):
                self.assertIn(landmark, _ui(fname),
                              "dau moc bien mat khoi %s - phep kiem da lac hau" % fname)
                self.assertIn(keyword, blob,
                              "sua %s (%s) ma khong patch nao nhac toi '%s' -> trinh duyet "
                              "van chay ma cu" % (fname, landmark, keyword))


# ---------------------------------------------------------------------------------------
# Ban ke ma bam - thay cho viec nho tay
#
# Danh sach dau moc o tren phai co NGUOI them vao moi lan sua HTML, nen no chi bat duoc thu
# ai do nho ghi. Ngay 31/08 no de lot mot ban sua that: `isMine` trong main_section.html bo
# nhanh `owner`, deploy sach, test xanh, va trang live van chay ma cu - vi main_section.html
# CHUA TUNG nam trong danh sach dau moc.
#
# Ban ke duoi day khong can nho: no giu ma bam noi dung cua TUNG template duoc bom vao trang.
# Sua mot ky tu trong template -> ma bam lech -> test do, kem loi nhac phai them patch resync
# roi cap nhat ban ke. Va danh sach template thi TU DO ra tu chinh cac module page_sync, nen
# them mot template moi cung khong lot duoc.
# ---------------------------------------------------------------------------------------

_SYNC_MODULES = [
    "approval_center/features/payment_request/infrastructure/page_sync.py",
    "platform/esign/ops_page_sync.py",
]
_TEMPLATE_DIRS = [
    "approval_center/features/payment_request/ui",
    "platform/esign/ui",
]


def _manifest():
    path = os.path.join(_ROOT, "approval_center", "patches", "resync_manifest.json")
    return json.loads(io.open(path, encoding="utf-8").read())


def _injected_templates():
    """Template nao that su duoc bom vao trang - doc tu chinh page_sync, khong liet ke tay."""
    out = set()
    for mod in _SYNC_MODULES:
        src = io.open(os.path.join(_ROOT, mod), encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if not node.value.endswith(".html"):
                continue
            for d in _TEMPLATE_DIRS:
                if os.path.exists(os.path.join(_ROOT, d, node.value)):
                    out.add(d + "/" + node.value)
    return out


def _sha(rel):
    raw = io.open(os.path.join(_ROOT, rel), "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


class TestManifestCoversEveryInjectedTemplate(unittest.TestCase):
    def setUp(self):
        self.man = _manifest()
        self.found = _injected_templates()
        self.assertTrue(self.found,
                        "khong doc duoc template nao tu page_sync - phep kiem nay dang mu")

    def test_khong_template_nao_dung_ngoai_ban_ke(self):
        missing = sorted(self.found - set(self.man))
        self.assertEqual(missing, [],
                         "template duoc bom vao trang nhung khong ai canh: %s" % missing)

    def test_ban_ke_khong_tro_vao_hu_khong(self):
        stale = sorted(set(self.man) - self.found)
        self.assertEqual(stale, [],
                         "ban ke con giu template khong con duoc bom vao dau ca: %s" % stale)

    def test_ma_bam_khop_hoac_phai_co_patch_moi(self):
        for rel, rec in sorted(self.man.items()):
            with self.subTest(template=rel):
                self.assertEqual(
                    _sha(rel), rec["sha256"],
                    "%s da doi noi dung. Sua template thoi thi KHONG AI THAY - phai them mot "
                    "patch goi page_sync.sync(), khai vao patches.txt, roi cap nhat sha256 o "
                    "resync_manifest.json." % rel)

    def test_patch_duoc_khai_va_ton_tai(self):
        patches = _patches()
        listed = io.open(os.path.join(_ROOT, "patches.txt"), encoding="utf-8").read()
        for rel, rec in sorted(self.man.items()):
            with self.subTest(template=rel):
                name = rec["last_resync_patch"]
                self.assertIn(name + ".py", patches,
                              "ban ke tro toi patch khong ton tai: %s" % name)
                self.assertIn(name, listed,
                              "patch %s chua khai trong patches.txt -> migrate khong chay"
                              % name)


if __name__ == "__main__":
    unittest.main()
