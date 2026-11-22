# Copyright (c) 2026, eCentric and contributors
"""Asset cua trang huong dan: mermaid vendor dung ban da ghim + dau ?v= khong lech.

  * mermaid.min.js phai khop sha256 trong PINNED.sha256 (ai sua tay / thay ban khac ma quen
    cap nhat ghi chep -> do). Khong CDN: trang chi duoc tro vao /assets/ecentric_workspace/.
  * moi the <link>/<script> tro vao public/guides|vendor/mermaid mang ?v= = 10 ky tu dau sha256
    noi dung (Frappe Cloud cache /assets mot nam). Lech -> python -m ecentric_workspace.guides.assets --stamp
    roi patch resync + resync_manifest.json.
"""
import hashlib
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)

from ecentric_workspace.guides import assets  # noqa: E402

VENDOR = os.path.join(assets.PUBLIC_DIR, "vendor", "mermaid")


class TestMermaidVendor(unittest.TestCase):
    def _pinned(self):
        meta, shas = {}, {}
        for line in io.open(os.path.join(VENDOR, "PINNED.sha256"), encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([0-9a-f]{64})\s+(\S+)$", line)
            if m:
                shas[m.group(2)] = m.group(1)
            elif ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, shas

    def test_ban_ghim_khop_tep(self):
        meta, shas = self._pinned()
        self.assertEqual(meta.get("version"), "10.9.1")
        self.assertIn("mermaid.min.js", shas)
        raw = io.open(os.path.join(VENDOR, "mermaid.min.js"), "rb").read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), shas["mermaid.min.js"],
                         "mermaid.min.js khong con la ban da ghim")
        self.assertTrue(os.path.isfile(os.path.join(VENDOR, "LICENSE")))

    def test_ban_ghim_la_umd_gan_window_mermaid(self):
        head = io.open(os.path.join(VENDOR, "mermaid.min.js"), encoding="utf-8").read(400)
        self.assertIn(".mermaid=", head)


class TestDauPhienBan(unittest.TestCase):
    def test_co_trang_nap_asset(self):
        self.assertGreaterEqual(len(assets.page_paths()), 9, "8 bai nhan su + muc luc")

    def test_khong_trang_nao_lech_v(self):
        for p in assets.page_paths():
            with self.subTest(page=os.path.basename(os.path.dirname(p))):
                self.assertEqual(assets.stale(io.open(p, encoding="utf-8").read()), [])

    def test_doi_noi_dung_thi_lech(self):
        html = '<script src="/assets/ecentric_workspace/guides/ec_guide_flow.js?v=0000000000"></script>'
        self.assertEqual(len(assets.stale(html)), 1)
        self.assertEqual(assets.stale(assets.stamp(html)), [])

    def test_tep_khong_ton_tai_thi_bao(self):
        html = '<script src="/assets/ecentric_workspace/guides/khong_co.js?v=abc"></script>'
        self.assertEqual(assets.stale(html), [("guides/khong_co.js", "abc", None)])


if __name__ == "__main__":
    unittest.main()
