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
import glob
import io
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


if __name__ == "__main__":
    unittest.main()
