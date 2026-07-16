# Copyright (c) 2026, eCentric and contributors
"""Phase 2B.1: /approval + /all-ticket repo-ization and shell migration contracts.

Zone law: everything OUTSIDE the shell chrome (embedded sidebar + topbar) is the
ACTION/BUSINESS ZONE and must remain byte-identical to the imported ground truth
(snapshot 20260716_004227). Endpoint census locks every legacy action path."""
import hashlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
LP = os.path.join(APP, "legacy_pages")

# Endpoint census from the 2B.1 design trace (counts as of ground truth).
APPROVAL_ENDPOINTS = {
    "ecentric_workspace.api.approval_decision": 2,
    "ecentric_workspace.api.get_ticket_detail": 2,
    "approve_contract": 2,
    "resubmit_gbs_doc": 1,
    "submit_gbs_doc": 1,
    "gbs_post_comment": 1,
    "gbs_fetch_comments": 1,
    "gbs_add_attachment": 1,
    "gbs_attach_upload_session": 1,
    "gbs_convert_attachments_to_anon": 1,
    "ecentric_workspace.gbs_comment_proxy.upload_image_to_boxme": 1,
    "manual_poll_gbs_status": 2,
    "gbs_poll_one_doc": 1,
    "gbs_force_poll_all": 1,
    "gbs_sync_all": 1,
    "gbs_so_create_po_helper": 1,
    "ec_get_unread": 1,
    "ec_mark_seen": 1,
}
ALLTICKET_ENDPOINTS = {
    "gbs_sync_all": 1,
    "gbs_force_poll_all": 1,
    "ec_get_unread": 1,
    "ec_mark_seen": 1,
}


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class TestEndpointCensus(unittest.TestCase):
    """Every legacy action path stays present with an unchanged call-site count."""

    def test_approval_endpoints_locked(self):
        src = _read(LP, "approval_page", "main_section.html")
        for ep, n in APPROVAL_ENDPOINTS.items():
            self.assertEqual(src.count("api/method/" + ep), n, ep)

    def test_all_ticket_endpoints_locked(self):
        src = _read(LP, "all_ticket", "main_section.html")
        for ep, n in ALLTICKET_ENDPOINTS.items():
            self.assertEqual(src.count("api/method/" + ep), n, ep)
        # no decision endpoints on the list page -- ever
        self.assertNotIn("approval_decision", src)

    def test_all_ticket_business_contracts(self):
        src = _read(LP, "all_ticket", "main_section.html")
        self.assertEqual(src.count("_ecSyncFilterToURL"), 2)      # URL-state helper
        self.assertEqual(src.count("_ecRestoreFilterFromURL"), 2)
        self.assertEqual(src.count("kpi-card"), 25)  # 19 KPI card elements = 25
        # string occurrences incl. CSS selectors -- locked to ground truth
        self.assertIn('href="/approval?', src)                    # row deep links
        self.assertIn("ec-all-tickets-gbs-cols", src)             # GBS columns injection marker

    def test_approval_business_contracts(self):
        src = _read(LP, "approval_page", "main_section.html")
        for marker in ("submitDecision", "openSendBackModal", "injectCanSuaBanner",
                       "ec-all-tickets-gbs-cols", "btnApprove", "btnReject"):
            self.assertIn(marker, src, marker)


class TestShellMigration(unittest.TestCase):
    """Shell chrome adopted; single-bell contract; business chrome retained."""

    def test_approval_shell_zone(self):
        src = _read(LP, "approval_page", "main_section.html")
        self.assertEqual(src.count('data-ec-shell="1"'), 1)
        self.assertEqual(src.count('data-ec-shell-header-right="1"'), 1)
        self.assertEqual(src.count('<aside class="ec-sidebar">'), 0)
        self.assertIn('class="ec-shell-fallback"', src)
        # the shell emits the ONLY bell at runtime; static page has none
        self.assertEqual(src.count("data-ec-notification-bell"), 0)
        # functional topbar-left business elements retained
        for marker in ('id="pageTitle"', 'id="tkId"', 'id="tkStatus"',
                       'class="back-btn" href="/all-ticket"'):
            self.assertIn(marker, src, marker)
        # Help/docs + Settings buttons preserved (locked scope)
        self.assertEqual(src.count('href="https://docs.ecentric.vn"'), 1)


    def test_all_ticket_shell_zone(self):
        src = _read(LP, "all_ticket", "main_section.html")
        self.assertEqual(src.count('data-ec-shell="1"'), 1)
        self.assertEqual(src.count('data-ec-shell-header-right="1"'), 1)
        self.assertEqual(src.count('<aside class="ec-sb">'), 0)
        self.assertIn('class="ec-shell-fallback"', src)
        self.assertEqual(src.count("data-ec-notification-bell"), 0)
        # hidden legacy .sidebar stays byte-present (dead markup, zero risk)
        self.assertIn('<aside class="sidebar">', src)
        self.assertIn('.dash-wrap > aside.sidebar { display: none !important; }', src)


class TestPageSyncModules(unittest.TestCase):
    def _mod(self, name):
        fake = types.ModuleType("frappe")
        fake.whitelist = lambda **kw: (lambda fn: fn)
        fake._ = lambda s: s
        fake.db = types.SimpleNamespace(exists=lambda *a: False)
        fake.session = types.SimpleNamespace(user="t@e.vn")
        fake.get_roles = lambda u=None: []
        fake.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a))
        sys.modules.setdefault("frappe", fake)
        import importlib
        sys.modules.pop("ecentric_workspace.legacy_pages." + name + ".page_sync", None)
        return importlib.import_module("ecentric_workspace.legacy_pages." + name + ".page_sync")

    def test_html_is_verbatim_file(self):
        for name, fname in (("approval_page", "approval_page"), ("all_ticket", "all_ticket")):
            mod = self._mod(name)
            self.assertEqual(mod._html(), _read(LP, fname, "main_section.html"),
                             name + ": _html() must be the exact file (idempotency)")

    def test_live_identity_constants(self):
        m1 = self._mod("approval_page")
        self.assertEqual((m1.ROUTE, m1.NAME, m1.TITLE), ("approval", "approval-page", "Approval"))
        m2 = self._mod("all_ticket")
        self.assertEqual((m2.ROUTE, m2.NAME, m2.TITLE), ("all-ticket", "all-ticket", "All Ticket"))


if __name__ == "__main__":
    unittest.main()
