# Copyright (c) 2026, eCentric and contributors
"""Daily Cockpit homepage contracts (Phase 2C.2).

The homepage is authored in-repo (legacy_pages/home) -- no snapshot import.
These tests lock: shell adoption, the 4-zone structure, the endpoint census,
registry-derived quick access, anti-drift counts, removal of every legacy
element the 2C.2 scope names, and the server-side chatbot preservation
contract in page_sync."""
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.shell import fallback as fb  # noqa: E402

HOME = os.path.join(APP, "legacy_pages", "home", "main_section.html")
SYNC = os.path.join(APP, "legacy_pages", "home", "page_sync.py")


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


class TestCockpitStructure(unittest.TestCase):
    def test_shell_and_canonical_header(self):
        src = _read(HOME)
        self.assertEqual(src.count('data-ec-shell="1"'), 1)
        self.assertEqual(src.count('data-ec-shell-topbar="1"'), 1)
        self.assertEqual(src.count('data-ec-shell-crumbs="1"'), 1)
        self.assertEqual(src.count('data-ec-notification-bell="1"'), 1)
        self.assertIn('<strong class="ec-shell-crumb-current">Trang chủ</strong>', src)
        self.assertIn("ec-shell-fallback", src)  # static sidebar, first paint

    def test_four_zones_present(self):
        src = _read(HOME)
        for z in ("ck-greet", "ck-attn", "ck-appr", 'data-ec-shell-quickaccess="1"'):
            self.assertIn(z, src, z)
        # buckets vocabulary incl. the explicit "Không hạn"
        for w in ("Quá hạn", "Hôm nay", "Sắp tới", "Không hạn"):
            self.assertIn(w, src, w)

    def test_intentional_empty_states(self):
        src = _read(HOME)
        self.assertIn("Không có việc nào cần xử lý", src)
        self.assertIn("Không có yêu cầu nào chờ bạn duyệt", src)

    def test_endpoint_census(self):
        src = _read(HOME)
        census = {
            "ecentric_workspace.action_center.api.get_action_items": 1,
            "ecentric_workspace.action_center.api.get_my_requests_summary": 1,
            "ecentric_workspace.shell.api.get_shell_boot": 1,
        }
        for ep, n in census.items():
            self.assertEqual(src.count(ep), n, ep)
        # deliberately dropped/retired endpoints & assets
        for gone in ("sso_get_profile", "action_center_widget.js",
                     "ec-action-center-widget"):
            self.assertEqual(src.count(gone), 0, gone)

    def test_legacy_elements_removed(self):
        src = _read(HOME)
        for gone in ("ecentric-app", 'class="nav-item', "/coming-soon",
                     "Cần cài Frappe HR", "Sẽ tích hợp Outlook",
                     "Chưa có chính sách", '{{'):
            self.assertEqual(src.count(gone), 0, gone)
        # no hardcoded-zero KPI cards: counts render only from provider JS
        self.assertNotIn('class="stat', src)

    def test_no_mojibake(self):
        src = _read(HOME)
        for m in ("Ã", "Ä", "â€", "á»"):
            self.assertEqual(src.count(m), 0, m)
        self.assertFalse(src.startswith("﻿"))


class TestQuickAccessRegistryParity(unittest.TestCase):
    def test_tiles_equal_registry_render(self):
        src = _read(HOME)
        m = fb.QUICKACCESS_RE.search(src)
        self.assertIsNotNone(m)
        inner = m.group(0)[len(m.group(1)):-len("</div>")]
        self.assertEqual(inner, fb.render_quickaccess_inner(),
                         "quick access drifted from the registry renderer")

    def test_no_second_route_catalog(self):
        # every /route in the quick-access zone must come from the registry
        src = _read(HOME)
        m = fb.QUICKACCESS_RE.search(src)
        import ecentric_workspace.shell.nav as nav
        known = set()
        for it in nav.compose_all():
            known.add(it["route"])
            for ch in it.get("children") or []:
                known.add(ch["route"])
        for href in re.findall(r'href="(/[^"]*)"', m.group(0)):
            self.assertIn(href, known, href)


class TestAntiDrift(unittest.TestCase):
    def test_counts_derive_from_rendered_payload(self):
        src = _read(HOME)
        # approvals-waiting list + count come from the SAME items array
        self.assertIn("items.filter(function (x) { return (x.source_type || x.source_key) === 'approval'", src)
        self.assertIn("'(' + appr.length + ')'", src)
        self.assertIn("'(' + items.length + ')'", src)
        # no independent count endpoint anywhere in the page
        self.assertNotIn("get_unread_count", src)
        self.assertNotIn("count(", src.lower().replace("appr.length", ""))


class TestBusinessPreservation(unittest.TestCase):
    def test_csrf_patch_byte_equal_to_governed_copy(self):
        src = _read(HOME)
        ref = _read(os.path.join(APP, "legacy_pages", "form_po", "main_section.html"))
        pat = re.compile(r'<script id="ec-csrf-fetch-patch">.*?</script>', re.S)
        a, b = pat.search(src), pat.search(ref)
        self.assertIsNotNone(a)
        self.assertEqual(a.group(0), b.group(0), "csrf patch drifted")

    def test_sync_preserves_live_chatbot_server_side(self):
        s = _read(SYNC)
        self.assertIn('CHATBOT_RE = re.compile(r\'<script id="ec-chatbot-js">.*?</script>\', re.S)', s)
        self.assertIn("_with_live_chatbot", s)
        self.assertIn('res["chatbot"] = chatbot', s)
        self.assertIn('ROUTE = "home"', s)
        self.assertIn('NAME = "ecentric-workspace"', s)
        self.assertIn("System Manager", s)          # SM-gated sync
        self.assertIn("ensure_static_serving", s)
        # Website Settings home_page must never be touched (docstring may
        # MENTION it; code must never reference the DocType as a string)
        self.assertNotIn('"Website Settings"', s)
        self.assertNotIn("set_value(\"Website Settings", s)


if __name__ == "__main__":
    unittest.main()
