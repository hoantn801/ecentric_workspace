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
#
# 31/08 (chieu): mo rong tu 5 template cua hai trang ra TOAN BO 42 module page_sync - 44
# template. Cai gi ban ke NOI VA KHONG NOI:
#
#   * No bat duoc: tu hom nay tro di, sua mot template ma khong kem patch resync.
#   * No KHONG bat duoc: nhung template DA troi tu truoc. Muc goi la `baseline` chi la anh
#     chup hien trang REPO ngay 31/08; no khong khang dinh gi ve ban dang chay tren site.
#     Muon biet trang nao dang troi thi phai doi chieu voi site, khong phai voi file nay.
# ---------------------------------------------------------------------------------------

#: Thu muc co the chua template, tinh tuong doi tu module page_sync.
def _candidate_dirs(mod_rel):
    d = os.path.dirname(mod_rel)                 # .../infrastructure
    parent = os.path.dirname(d)                  # .../<feature>
    return [os.path.join(parent, "ui"), d, os.path.join(d, "ui"),
            "platform/esign/ui", os.path.join(parent, "frontend")]


#: Tham chieu .html khong co file thuc trong repo. Moi muc phai co ly do, khong phai cho de
#: nem thu minh chua giai duoc vao.
_KNOWN_MISSING = {
    ("legacy_pages/home/page_sync.py", "main_section.html"):
        "Trang chu KHONG co baseline trong repo (BASELINE_SHA256 = None) - sua trang chu la "
        "ghi thang len production. Xem chu thich dau legacy_pages/home/page_sync.py.",
}


_CACHE = {}


def _sync_modules():
    """Moi module page_sync co ham sync() - quet ra, khong liet ke tay.

    Nho ket qua: quet ca cay nguon mat ~9 giay, va mot bo test chay 90 giay la mot bo test
    nguoi ta bat dau bo qua.
    """
    if "mods" in _CACHE:
        return _CACHE["mods"]
    out = []
    for path in sorted(glob.glob(os.path.join(_ROOT, "**", "*.py"), recursive=True)):
        if "page_sync" not in os.path.basename(path):
            continue
        src = io.open(path, encoding="utf-8").read()
        if "def sync" not in src:
            continue
        out.append(os.path.relpath(path, _ROOT).replace(os.sep, "/"))
    _CACHE["mods"] = out
    return out


def _manifest():
    path = os.path.join(_ROOT, "approval_center", "patches", "resync_manifest.json")
    return json.loads(io.open(path, encoding="utf-8").read())


def _injected_templates():
    """Template nao that su duoc bom vao trang - doc tu chinh page_sync, khong liet ke tay.

    Tra ve (da_giai, chua_giai) de mot tham chieu .html khong tim thay file KHONG bien mat
    im lang: no phai nam trong _KNOWN_MISSING kem ly do, hoac lam test do.
    """
    if "tpl" in _CACHE:
        return _CACHE["tpl"]
    found, missing = set(), set()
    for mod in _sync_modules():
        src = io.open(os.path.join(_ROOT, mod), encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if not node.value.endswith(".html"):
                continue
            hit = None
            for d in _candidate_dirs(mod):
                rel = os.path.join(d, node.value).replace(os.sep, "/")
                if os.path.exists(os.path.join(_ROOT, rel)):
                    hit = rel
                    break
            if hit:
                found.add(hit)
            else:
                missing.add((mod, node.value))
    _CACHE["tpl"] = (found, missing)
    return found, missing


def _sha(rel):
    raw = io.open(os.path.join(_ROOT, rel), "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


class TestManifestCoversEveryInjectedTemplate(unittest.TestCase):
    def setUp(self):
        self.man = _manifest()
        self.found, self.missing = _injected_templates()
        self.assertGreater(len(self.found), 30,
                           "chi tim thay %d template tu 42 module page_sync - cach doc AST "
                           "da khong theo kip code, phep kiem dang mu" % len(self.found))

    def test_moi_module_page_sync_deu_duoc_quet(self):
        """Nguong tong khong du - mot module bi doc thanh rong phai lam test do."""
        mods = _sync_modules()
        self.assertGreater(len(mods), 35,
                           "chi quet duoc %d module page_sync - truoc day co 42" % len(mods))

    def test_khong_template_nao_dung_ngoai_ban_ke(self):
        missing = sorted(self.found - set(self.man))
        self.assertEqual(missing, [],
                         "template duoc bom vao trang nhung khong ai canh: %s" % missing)

    def test_ban_ke_khong_tro_vao_hu_khong(self):
        stale = sorted(set(self.man) - self.found)
        self.assertEqual(stale, [],
                         "ban ke con giu template khong con duoc bom vao dau ca: %s" % stale)

    def test_tham_chieu_khong_giai_duoc_phai_co_ly_do(self):
        """Mot .html khong tim thay file KHONG duoc bien mat im lang.

        `legacy_pages/home` la ngoai le that: trang chu khong co baseline trong repo. Nhung
        neu mai mot module khac cung roi vao trang thai do vi mot ly do khac han - doi ten
        thu muc, doi quy uoc - thi phai co nguoi nhin thay va viet ra, khong phai de no lang
        le tuot khoi tam kiem.
        """
        unexplained = sorted(m for m in self.missing if m not in _KNOWN_MISSING)
        self.assertEqual(unexplained, [],
                         "tham chieu .html khong tim thay file va khong co ly do: %s"
                         % unexplained)

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
            name = rec.get("last_resync_patch")
            if name is None:
                # Muc `baseline`: anh chup hien trang repo 31/08, chua gan voi patch nao. No
                # van bi rang buoc boi ma bam o tren - lan sua TIEP THEO se phai co patch.
                self.assertIn("baseline", rec,
                              "muc khong co patch phai tu khai la baseline: %s" % rel)
                continue
            with self.subTest(template=rel):
                self.assertIn(name + ".py", patches,
                              "ban ke tro toi patch khong ton tai: %s" % name)
                self.assertIn(name, listed,
                              "patch %s chua khai trong patches.txt -> migrate khong chay"
                              % name)


if __name__ == "__main__":
    unittest.main()
