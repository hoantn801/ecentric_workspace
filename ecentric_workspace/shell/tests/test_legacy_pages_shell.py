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
    # C4b (2026-08-03): was 2, now 3. The Send back flow for the three NATIVE
    # types (MSO / Sales Order / Purchase Order) reads the document through
    # get_ticket_detail instead of /api/resource, because 57 of 119 enabled
    # users are Website Users and would get 403 reading the DocType directly --
    # and because only get_ticket_detail returns `status` normalised from
    # workflow_state plus the revision_reason / revision_count keys the
    # "Can sua" banner needs. See fetchDoc() in approval_page/main_section.html.
    "ecentric_workspace.api.get_ticket_detail": 3,
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


# #138 (2026-08-03): the 4 legacy creation forms (mso_form, so_form, form_po,
# form_rec) were REMOVED from the repo -- see LIVE_PAGES / TestPageSyncGuards
# below. TestCreationForms and its FORM_PAGES / FORM_ENDPOINTS censuses went
# with them; the live creation forms are /mso-plan-form, /gbs-so-form-v2 and
# /gbs-po-form-v2.
#
# #61 (2026-08-03): those three were still SITE-ONLY -- they existed on
# team.ecentric.vn and nowhere else, so a rebuild would have lost them and no
# review could see what they contained. They are now imported VERBATIM (byte
# round-trip verified against live) and join LIVE_PAGES, which means they are
# covered by the Jinja-free scan, the static-serving wiring census and the
# drift-lock guards below like every other repo-owned legacy page.

# The only legacy_pages folders that ship a repo snapshot + page_sync.
# home is separate: it is guarded/zero-write and has no main_section.html.
LIVE_PAGES = ("all_ticket", "approval_page", "docs_architecture", "docs_gbsflow",
              "gbs_po_form_v2", "gbs_so_form_v2", "mso_plan_form")


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


class TestMojibakeGuard(unittest.TestCase):
    """PRODUCTION-BLOCKER regression guard (2026-07-16): the PS1 snapshot
    pipeline emits DOUBLE-ENCODED UTF-8 (utf-8 bytes decoded as latin-1 and
    re-encoded) plus a BOM. Any repo page source must be clean single-encoded
    Vietnamese. Never import snapshot HTML without the latin-1 reversal."""

    FORBIDDEN = ["Ã", "Ä", "â€"]
    # ONE pre-existing blemish lived on production /approval BEFORE 2B.1
    # ('Chờ ảnh upload xong' double-encoded by an old PS1 deploy). We preserve
    # last-known-good live bytes -- exactly one pinned instance is tolerated.
    # NOTE: the \uXXXX escapes below ARE the mojibake characters (already
    # decoded by Python) -- do not re-decode them.
    APPROVAL_KNOWN_BLEMISH = "Ch\u00e1\u00bb\u009d \u00e1\u00ba\u00a3nh upload xong"

    def _scan(self, path_parts, allow_ao=0, pin=None):
        src = _read(*path_parts)
        for m in self.FORBIDDEN:
            self.assertEqual(src.count(m), 0, "%s in %s" % (m, path_parts[-2:]))
        self.assertEqual(src.count("á»"), allow_ao, path_parts[-2:])
        if pin:
            self.assertIn(pin, src)
        self.assertFalse(src.startswith("\ufeff"), "BOM must be stripped")

    def test_legacy_pages_clean(self):
        self._scan((LP, "approval_page", "main_section.html"), allow_ao=1,
                   pin=self.APPROVAL_KNOWN_BLEMISH)
        self._scan((LP, "all_ticket", "main_section.html"), allow_ao=0)

    def test_representative_vietnamese_intact(self):
        src = _read(LP, "approval_page", "main_section.html")
        for w in ("Trang chủ", "Đang tải chi tiết", "Nhắc việc", "Cài đặt",
                  "Điều hướng eCentric"):
            self.assertIn(w, src, w)

    def test_all_approval_frontends_clean(self):
        fe = os.path.join(APP, "approval_center", "frontend")
        for fname in sorted(os.listdir(fe)):
            if fname.endswith(".html"):
                src = _read(fe, fname)
                for m in self.FORBIDDEN + ["á»"]:
                    self.assertEqual(src.count(m), 0, "%s in %s" % (m, fname))


class TestShellMigration(unittest.TestCase):
    """Shell chrome adopted; single-bell contract; business chrome retained."""

    def test_approval_shell_zone(self):
        src = _read(LP, "approval_page", "main_section.html")
        self.assertEqual(src.count('data-ec-shell="1"'), 1)
        self.assertEqual(src.count('data-ec-shell-header-right="1"'), 1)
        self.assertEqual(src.count('<aside class="ec-sidebar">'), 0)
        self.assertIn('ec-shell-fallback', src)
        # exactly ONE static bell, inside the header-right slot
        self.assertEqual(src.count('data-ec-notification-bell="1"'), 1)
        # functional topbar-left business elements retained
        for marker in ('id="pageTitle"', 'id="tkId"', 'id="tkStatus"',
                       'class="back-btn" href="/all-ticket"'):
            self.assertIn(marker, src, marker)
        # Global Header phase: redundant Home/Help/legacy-Settings icons are
        # REMOVED from the global header (Home + Help live in the sidebar).
        self.assertEqual(src.count('href="https://docs.ecentric.vn"'), 0)
        self.assertEqual(src.count('class="icon-btn"'), 0)


    def test_all_ticket_shell_zone(self):
        src = _read(LP, "all_ticket", "main_section.html")
        self.assertEqual(src.count('data-ec-shell="1"'), 1)
        self.assertEqual(src.count('data-ec-shell-header-right="1"'), 1)
        self.assertEqual(src.count('<aside class="ec-sb">'), 0)
        self.assertIn('ec-shell-fallback', src)
        self.assertEqual(src.count('data-ec-notification-bell="1"'), 1)
        # hidden legacy .sidebar stays byte-present (dead markup, zero risk)
        self.assertIn('<aside class="sidebar">', src)
        self.assertIn('.dash-wrap > aside.sidebar { display: none !important; }', src)


class TestStaticServingSafety(unittest.TestCase):
    """Part D: dynamic_template=0 is only safe because every legacy page is
    Jinja-free (identical HTML for all users; personal data via APIs)."""

    def test_all_legacy_pages_jinja_free(self):
        for slug in sorted(os.listdir(LP)):
            f = os.path.join(LP, slug, "main_section.html")
            if not os.path.isfile(f):
                continue
            src = _read(LP, slug, "main_section.html")
            self.assertNotIn("{{", src, slug)
            self.assertNotIn("{%", src, slug)

    def test_all_page_syncs_wire_static_serving(self):
        n = 0
        for slug in sorted(os.listdir(LP)):
            ps = os.path.join(LP, slug, "page_sync.py")
            if not os.path.isfile(ps):
                continue
            if slug == "home":
                # Homepage Sync Safety Hotfix: home is GUARDED (zero-write) and
                # EXEMPT from static serving -- the live page carries Jinja.
                self.assertNotIn("ensure_static_serving", _read(LP, slug, "page_sync.py"))
                continue
            self.assertIn("ensure_static_serving", _read(LP, slug, "page_sync.py"), slug)
            n += 1
        # #138: was 13; 9 dead folders deleted 2026-08-03, leaving 4.
        # #61: +3 (mso_plan_form, gbs_so_form_v2, gbs_po_form_v2) imported from
        # live the same day, so the census is back to len(LIVE_PAGES) = 7.
        self.assertEqual(n, len(LIVE_PAGES))  # home exempt, guarded

    def test_serving_module_fail_open(self):
        src = _read(os.path.dirname(LP), "legacy_pages", "serving.py")
        self.assertIn("ec_legacy_static_serving_disabled", src)   # kill switch
        self.assertIn("except Exception", src)                    # fail-open
        self.assertIn('"{{"', src.replace("'", '"'))              # jinja guard


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
        # #61: every repo-owned legacy page, not just the original two. _html()
        # must hand back the file byte-for-byte, otherwise BASELINE_SHA256 (which
        # is the sha of the FILE) would not describe what sync() actually writes
        # and the drift lock would refuse on a site that never drifted.
        for name in LIVE_PAGES:
            mod = self._mod(name)
            self.assertEqual(mod._html(), _read(LP, name, "main_section.html"),
                             name + ": _html() must be the exact file (idempotency)")

    def test_live_identity_constants(self):
        # ROUTE/NAME/TITLE must equal what live already holds, or the first sync
        # after deploy would "update" instead of returning "unchanged".
        expected = {
            "approval_page": ("approval", "approval-page", "Approval"),
            "all_ticket": ("all-ticket", "all-ticket", "All Ticket"),
            # #61, read off live team.ecentric.vn at import time:
            "mso_plan_form": ("mso-plan-form", "mso-plan-form", "MSO Plan Form"),
            "gbs_so_form_v2": ("gbs-so-form-v2", "gbs-so-form-v2", "gbs-so-form-v2"),
            "gbs_po_form_v2": ("gbs-po-form-v2", "gbs-po-form-v2", "gbs-po-form-v2"),
        }
        for name, want in expected.items():
            m = self._mod(name)
            self.assertEqual((m.ROUTE, m.NAME, m.TITLE), want, name)


class TestPageSyncGuards(unittest.TestCase):
    """#138 (2026-08-03). A repo snapshot must never silently win over live.

    Every surviving page_sync must (a) pass publish=None so a page an operator
    deliberately un-published is NOT re-published, and (b) pin BASELINE_SHA256 to
    the sha256 of its own main_section.html so upsert_web_page REFUSES to write
    when live has drifted since the snapshot was taken. Updating a page on
    purpose therefore means re-snapshotting live AND bumping the constant in the
    same commit -- exactly the rule agreed for legacy page ownership."""

    def test_guards_present_and_baseline_matches_snapshot(self):
        for slug in LIVE_PAGES:
            src = _read(LP, slug, "page_sync.py")
            self.assertIn("publish=None", src, slug)
            self.assertIn("expect_sha=", src, slug)
            self.assertIn('res.get("action") == "refused"', src, slug)
            ns = {}
            for line in src.splitlines():
                if line.startswith("BASELINE_SHA256"):
                    exec(line, ns)          # noqa: S102 -- a single literal assignment
                    break
            self.assertIn("BASELINE_SHA256", ns, slug + ": missing BASELINE_SHA256")
            with open(os.path.join(LP, slug, "main_section.html"), "rb") as fh:
                want = hashlib.sha256(fh.read()).hexdigest()
            self.assertEqual(ns["BASELINE_SHA256"], want,
                             slug + ": BASELINE_SHA256 must be the sha256 of "
                                    "main_section.html (re-snapshot and bump together)")

    def test_endpoints_cannot_force(self):
        """The whitelisted POST endpoints stay no-arg: no caller can pass force=1
        and drop the drift lock over HTTP."""
        for slug in LIVE_PAGES:
            src = _read(LP, slug, "page_sync.py")
            self.assertIn("def sync(html=None, force=0)", src, slug)
            for line in src.splitlines():
                if line.startswith("def sync_") and line.rstrip().endswith("():"):
                    break
            else:
                self.fail(slug + ": whitelisted endpoint must take no arguments")

    def test_util_defaults_are_backward_compatible(self):
        """Any caller that passes neither guard keeps the historical behaviour."""
        src = _read(APP, "approval_center", "page_sync_util.py")
        self.assertIn("def upsert_web_page(route, name, title, html, publish=1, expect_sha=None)", src)
        self.assertIn("def content_sha256(", src)
        self.assertIn('"action": "refused"', src)
        # #144: the third publish mode. "preserve" keeps live's flag on an
        # existing page but creates a NEW page published -- publish=None would
        # create it hidden and the route would 404 until somebody noticed.
        self.assertIn('if publish == "preserve":', src)
        self.assertIn("want_published = doc.published if existing else 1", src)
        self.assertIn("want_published = doc.published if existing else 0", src)


class TestApprovalCenterPageSyncGuards(unittest.TestCase):
    """#144 (2026-08-03). The legacy pages were locked down under #138, but the
    27 Approval Center page_sync modules were still unguarded: each one would
    overwrite its live Web Page with the repo snapshot on any call, so a single
    stray POST to a sync endpoint could revert an edit made on the site.

    Every module must now (a) pass publish="preserve", (b) pin a BASELINE_SHA256
    so upsert_web_page REFUSES to write on live drift, and (c) keep its
    whitelisted endpoint argument-free so force=1 is unreachable over HTTP.

    BASELINE_SHA256 here is the sha of what _html() RETURNS, not of a file on
    disk: several modules compose their HTML (payment_request injects the e-sign
    panel, dashboard stitches sections), so there is no single file to hash.
    That is why this test checks shape and presence only; the byte-level match
    against live was verified at import time and is re-checked by sync() itself
    every time it runs."""

    AC = os.path.join(APP, "approval_center")

    def _modules(self):
        """EVERY sync module under approval_center, at any depth.

        The first sweep of #144 walked approval_center/<type>/page_sync.py only
        and therefore missed hub_page_sync.py, which sits directly under
        approval_center/ and syncs the /approvals HUB -- the most-visited page of
        the lot, and at that point the only one still running with both guards
        off. Walking the tree instead of globbing one fixed depth is what stops
        that from happening again: a new module in a new place is picked up
        automatically and fails this test until it is guarded."""
        for root, _dirs, files in os.walk(self.AC):
            if "__pycache__" in root or "/tests" in root.replace(os.sep, "/"):
                continue
            for f in sorted(files):
                if f == "page_sync.py" or f.endswith("_page_sync.py"):
                    rel = os.path.relpath(os.path.join(root, f), self.AC)
                    yield rel, _read(root, f)

    def test_every_module_is_guarded(self):
        n = 0
        for slug, src in self._modules():
            n += 1
            self.assertIn('publish="preserve"', src, slug + ": missing publish=preserve")
            self.assertIn("expect_sha=None if force else", src, slug + ": missing drift lock")
            self.assertIn("def sync(html=None, force=0)", src, slug + ": sync() signature")
            ns = {}
            for line in src.splitlines():
                if line.startswith("BASELINE_SHA256"):
                    exec(line, ns)          # noqa: S102 -- a single literal assignment
                    break
            self.assertIn("BASELINE_SHA256", ns, slug + ": missing BASELINE_SHA256")
            self.assertRegex(ns["BASELINE_SHA256"], r"^[0-9a-f]{64}$",
                             slug + ": BASELINE_SHA256 must be a sha256 hex digest")
            self.assertIn("SUPERSEDES_SHA256", src, slug + ": missing SUPERSEDES_SHA256")
        # 27 per-type modules + hub_page_sync.py (/approvals).
        self.assertEqual(n, 28, "expected 28 Approval Center sync modules, found %d" % n)

    def test_no_module_hand_rolls_its_own_upsert(self):
        """7 modules used to carry a private copy of the lookup/insert/update
        logic, which is exactly why the drift lock could not reach them. They all
        delegate to the shared helper now, and must keep doing so."""
        for slug, src in self._modules():
            self.assertIn("page_sync_util.upsert_web_page(", src, slug)
            for hand_rolled in ("frappe.new_doc(\"Web Page\")", "doc.save(ignore_permissions=True)"):
                self.assertNotIn(hand_rolled, src,
                                 slug + ": re-implements the upsert instead of delegating")

    def test_endpoints_cannot_force(self):
        """No caller can pass force=1 and disarm the drift lock over HTTP."""
        for slug, src in self._modules():
            for line in src.splitlines():
                if line.startswith("def sync_") and line.rstrip().endswith("():"):
                    break
            else:
                self.fail(slug + ": whitelisted endpoint must take no arguments")


if __name__ == "__main__":
    unittest.main()
