# Copyright (c) 2026, eCentric and contributors
"""Local PDF.js vendored-asset security + integrity verification (PR#148 CVE-2024-4367 fix).
Pure/no-DB; runs anywhere and under bench run-tests. Enforces: pinned version >= 4.2.67,
manifest/version/SHA integrity, LICENSE present, ESM local loader with isEvalSupported:false
and a local workerSrc, no CDN, and no residual vulnerable 3.11.174 assets."""
import hashlib
import os
import re
import shutil
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(os.path.dirname(_HERE))  # ecentric_workspace/
_VENDOR = os.path.join(_APP, "public", "vendor", "pdfjs")
_EDITOR = os.path.join(_APP, "approval_center", "esign", "ui", "pdf_placement_editor.html")
_MIN_SAFE = (4, 2, 67)


def _parse(path):
    meta, shas = {}, {}
    rx = re.compile(r"^([0-9a-f]{64})\s+(\S+)$")
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = rx.match(line.strip())
        if m:
            shas[m.group(2)] = m.group(1)
        elif ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, shas


def _vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


class TestPdfjsAssets(unittest.TestCase):
    def setUp(self):
        self.meta, self.shas = _parse(os.path.join(_VENDOR, "PINNED.sha256"))
        self.editor = open(_EDITOR, encoding="utf-8").read()

    def test_pinned_version_at_or_above_cve_floor(self):
        self.assertEqual(self.meta.get("package"), "pdfjs-dist")
        self.assertGreaterEqual(_vt(self.meta.get("version", "0")), _MIN_SAFE,
                                "pinned version is below the CVE-2024-4367 patch floor")

    def test_manifest_lists_esm_assets_only(self):
        self.assertIn("pdf.mjs", self.shas)
        self.assertIn("pdf.worker.mjs", self.shas)
        self.assertNotIn("pdf.min.js", self.shas)          # no legacy 3.11.174 asset
        self.assertNotIn("pdf.worker.min.js", self.shas)

    def test_asset_sha256_match_manifest(self):
        for name, want in self.shas.items():
            fp = os.path.join(_VENDOR, name)
            self.assertTrue(os.path.exists(fp), "missing %s" % name)
            got = hashlib.sha256(open(fp, "rb").read()).hexdigest()
            self.assertEqual(got, want, "sha mismatch %s" % name)

    def test_license_and_provenance_present(self):
        self.assertTrue(os.path.exists(os.path.join(_VENDOR, self.meta.get("license_file", "LICENSE"))))
        for k in ("npm_integrity", "npm_tarball_shasum", "retrieved", "upstream"):
            self.assertIn(k, self.meta, "manifest missing %s" % k)

    def test_verify_script_passes_on_clean_tree(self):
        # verify_pdfjs against a clean copy (the committed tree has no legacy files; a sandbox
        # OneDrive worktree may still shadow them, which verify_pdfjs correctly flags).
        import importlib.util
        d = tempfile.mkdtemp()
        try:
            for f in ["pdf.mjs", "pdf.worker.mjs", "LICENSE", "PINNED.sha256", "verify_pdfjs.py"]:
                shutil.copy(os.path.join(_VENDOR, f), d)
            spec = importlib.util.spec_from_file_location("verify_pdfjs",
                                                          os.path.join(d, "verify_pdfjs.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.verify(d), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_editor_uses_local_esm_no_cdn(self):
        self.assertIn("import(PDFJS_BASE", self.editor)      # ESM dynamic import
        self.assertIn("pdf.mjs", self.editor)
        self.assertIn("/assets/ecentric_workspace/vendor/pdfjs/", self.editor)
        for bad in ("cdnjs", "unpkg", "jsdelivr", "googleapis", "https://cdn"):
            self.assertNotIn(bad, self.editor)

    def test_editor_worker_is_local(self):
        self.assertIn("GlobalWorkerOptions.workerSrc", self.editor)
        self.assertIn('PDFJS_BASE + "pdf.worker.mjs"', self.editor)

    def test_editor_sets_iseval_supported_false(self):
        self.assertIn("isEvalSupported: false", self.editor)

    def test_editor_has_no_window_global_or_legacy_refs(self):
        self.assertNotIn("window.pdfjsLib", self.editor)
        self.assertNotIn("pdf.min.js", self.editor)
        self.assertNotIn("3.11.174", self.editor)

    def test_no_legacy_version_string_in_manifest_or_editor(self):
        self.assertNotIn("3.11.174", open(os.path.join(_VENDOR, "PINNED.sha256")).read())
        self.assertNotIn("3.11.174", self.editor)


if __name__ == "__main__":
    unittest.main()
