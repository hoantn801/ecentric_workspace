# Copyright (c) 2026, eCentric and contributors
"""Action Center resolver tests.

These exercise resolve_item + the URL builders. The Frappe-aware ones do
defensive get_value lookups; we monkey-patch frappe.db.get_value where
necessary so the tests run without specific seed data.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.action_center import resolvers


class TestActionCenterResolvers(FrappeTestCase):
    def test_build_approval_url_lowercases_and_underscores_type(self):
        # Spaces in DocType name -> underscores in `type` param.
        u = resolvers.build_approval_url("GBS Purchase Order", "GBS-PO-20260612-02710")
        self.assertIn("/approval?id=GBS-PO-20260612-02710", u)
        self.assertIn("&type=gbs_purchase_order", u)
        self.assertNotIn(" ", u)  # encoded

    def test_build_approval_url_url_encodes_name(self):
        # Names with spaces / special chars must be URL-encoded.
        u = resolvers.build_approval_url("Sales Order", "SO with space/&q")
        self.assertNotIn(" ", u)
        # Forward-slash and ampersand are part of unsafe chars -> encoded.
        self.assertIn("%20", u)
        self.assertIn("%2F", u.upper())
        self.assertIn("%26", u.upper())

    def test_build_wtu_url_encodes_label(self):
        self.assertEqual(resolvers.build_wtu_url("2026-W25"),
                         "/weekly-update?week=2026-W25")
        # Edge: a label containing whitespace must encode.
        self.assertEqual(resolvers.build_wtu_url("2026 W25"),
                         "/weekly-update?week=2026%20W25")

    def test_build_task_url_desk_form_unchanged_for_notifications(self):
        # build_task_url stays the Desk form (notification subsystem consumer);
        # byte-for-byte unchanged in Phase 1b.2.
        self.assertEqual(resolvers.build_task_url("TASK-2026-00084"),
                         "/app/task/TASK-2026-00084")
        self.assertEqual(resolvers.build_task_url("TASK 100/200"),
                         "/app/task/TASK%20100%2F200")

    def test_build_approval_center_url(self):
        # Phase 1b.3: canonical Approval Center form deep-link (EC Approval
        # Type.route + ?id=<business name>).
        self.assertEqual(
            resolvers.build_approval_center_url("/approvals/ai-topup", "EC-AITOP-1"),
            "/approvals/ai-topup?id=EC-AITOP-1")
        # missing leading slash is added
        self.assertEqual(
            resolvers.build_approval_center_url("approvals/ai-topup", "X"),
            "/approvals/ai-topup?id=X")
        # empty route -> empty (caller falls back, never a dead link)
        self.assertEqual(resolvers.build_approval_center_url("", "X"), "")
        # id is URL-encoded
        self.assertEqual(
            resolvers.build_approval_center_url("/approvals/x", "A/B C"),
            "/approvals/x?id=A%2FB%20C")

    def test_apply_approval_normalization_sets_approval_source_and_preserves_ref(self):
        item = {"reference_type": "EC AI Topup Request", "reference_name": "EC-AITOP-1",
                "source_type": "generic", "source_key": "generic",
                "action_url": "/app/ec-ai-topup-request/EC-AITOP-1", "title": "EC-AITOP-1"}
        resolvers.apply_approval_normalization(item, "REQ-1", "/approvals/ai-topup", "EC-AITOP-1")
        self.assertEqual(item["source_type"], "approval")
        self.assertEqual(item["source_key"], "approval")
        self.assertEqual(item["action_url"], "/approvals/ai-topup?id=EC-AITOP-1")
        self.assertEqual(item["source_name"], "REQ-1")
        self.assertEqual(item["approval_request"], "REQ-1")
        # business reference fields preserved for display/audit
        self.assertEqual(item["reference_type"], "EC AI Topup Request")
        self.assertEqual(item["reference_name"], "EC-AITOP-1")

    def test_apply_approval_normalization_fulfillment_stage(self):
        item = {"reference_type": "EC AI Topup Request", "reference_name": "EC-AITOP-1",
                "source_type": "generic", "source_key": "generic",
                "action_url": "/app/ec-ai-topup-request/EC-AITOP-1", "title": "EC-AITOP-1"}
        resolvers.apply_approval_normalization(
            item, "REQ-1", "/approvals/ai-topup", "EC-AITOP-1", stage="fulfillment")
        self.assertEqual(item["source_family"], "approval")
        self.assertEqual(item["action_stage"], "fulfillment")
        self.assertEqual(item["source_type"], "approval")           # family (backward compat)
        self.assertEqual(item["source_label"], "THỰC HIỆN")
        self.assertEqual(item["action_url"], "/approvals/ai-topup?id=EC-AITOP-1")
        # approval stage keeps the approve label
        item2 = dict(item)
        resolvers.apply_approval_normalization(item2, "REQ-1", "/approvals/ai-topup", "EC-AITOP-1")
        self.assertEqual(item2["action_stage"], "approval")
        self.assertEqual(item2["source_label"], "PHÊ DUYỆT")

    def test_has_engine_approval_link_is_metadata_driven(self):
        # Real approval-center DocType carries approval_request Link(EC Approval Request).
        resolvers._META_FIELD_CACHE.clear()
        self.assertTrue(resolvers.has_engine_approval_link("EC AI Topup Request"))
        # A non-approval DocType does not.
        self.assertFalse(resolvers.has_engine_approval_link("ToDo"))
        # Never hardcodes the 28 approval DocTypes: the detection reads meta.
        self.assertFalse(resolvers.has_engine_approval_link(""))

    def test_build_pm_task_url_is_spa_deep_link(self):
        # Phase 1b.2: the Action Center's canonical PM Task destination is the
        # portal SPA detail deep-link, NOT the Desk form.
        self.assertEqual(resolvers.build_pm_task_url("TASK-2026-00084"),
                         "/pm#task/TASK-2026-00084")
        self.assertNotIn("/app/task", resolvers.build_pm_task_url("TASK-2026-00084"))
        # Name with non-trivial chars: slash-encoded so the SPA router keeps it
        # in ONE hash segment (hash.split('/') -> decodeURIComponent).
        self.assertEqual(resolvers.build_pm_task_url("TASK 100/200"),
                         "/pm#task/TASK%20100%2F200")

    def test_desk_fallback_slug_uses_dashes_not_underscore_or_dot(self):
        u = resolvers.build_desk_fallback_url("Brand Approver Special", "BA-1")
        # Slug = lowercase, spaces -> dashes.
        self.assertTrue(u.startswith("/app/brand-approver-special/"))
        # Underscores ALSO collapse to dashes (Frappe slug convention).
        u2 = resolvers.build_desk_fallback_url("Some_Custom_Type", "X-1")
        self.assertTrue(u2.startswith("/app/some-custom-type/"))

    # ---- resolve_item routing ---------------------------------------------

    def test_resolve_wtu_routes_to_weekly_update(self):
        # Monkey-patch get_value to return a week label.
        orig = frappe.db.get_value
        def _get(dt, name, field, **kw):
            if dt == "Weekly Team Update" and field == "week_label":
                return "2026-W25"
            return orig(dt, name, field, **kw)
        frappe.db.get_value = _get
        try:
            item = resolvers.resolve_item({
                "name": "todo-1", "reference_type": "Weekly Team Update",
                "reference_name": "WTU-2026-W25-EMP-1",
                "description": "", "priority": "Medium", "modified": "",
            })
            self.assertEqual(item["source_key"], "weekly_report")
            self.assertEqual(item["source_label"], "BÁO CÁO TUẦN")
            self.assertEqual(item["action_label"], "Điền báo cáo")
            self.assertTrue(item["action_url"].startswith("/weekly-update?week="))
            self.assertNotIn("/approval", item["action_url"])
        finally:
            frappe.db.get_value = orig

    def test_resolve_approval_returns_approval_url(self):
        orig = frappe.db.get_value
        def _get(dt, name, field, **kw):
            # Don't fail on title/name lookup -- return None so resolver uses ref_name.
            return None
        frappe.db.get_value = _get
        try:
            item = resolvers.resolve_item({
                "name": "todo-2", "reference_type": "GBS Purchase Order",
                "reference_name": "GBS-PO-20260612-02710",
                "description": "", "priority": "High", "modified": "",
            })
            self.assertEqual(item["source_key"], "approval")
            self.assertEqual(item["source_label"], "PHÊ DUYỆT")
            self.assertEqual(item["action_label"], "Phê duyệt")
            self.assertEqual(
                item["action_url"],
                "/approval?id=GBS-PO-20260612-02710&type=gbs_purchase_order",
            )
        finally:
            frappe.db.get_value = orig

    def test_resolve_task_routes_to_pm_spa(self):
        orig = frappe.db.get_value
        def _get(dt, name, field, **kw):
            if dt == "Task" and field == "subject":
                return "Design homepage"
            return None
        frappe.db.get_value = _get
        try:
            item = resolvers.resolve_item({
                "name": "todo-3", "reference_type": "Task",
                "reference_name": "TASK-2026-00084",
                "description": "", "priority": "Medium", "modified": "",
            })
            self.assertEqual(item["source_key"], "task")
            self.assertEqual(item["source_label"], "CÔNG VIỆC")
            self.assertEqual(item["action_label"], "Xem công việc")
            # Canonical PM SPA task detail -- not the Desk form.
            self.assertEqual(item["action_url"], "/pm#task/TASK-2026-00084")
            self.assertNotIn("/app/task", item["action_url"])
            self.assertEqual(item["title"], "Design homepage")
            self.assertNotIn("/approval", item["action_url"])
        finally:
            frappe.db.get_value = orig

    # ---- canonical routing guarantees (Phase 1b.2) ------------------------

    def _resolve(self, ref_type, ref_name, desc="", name="todo-x"):
        orig = frappe.db.get_value
        frappe.db.get_value = lambda *a, **kw: None
        try:
            return resolvers.resolve_item({
                "name": name, "reference_type": ref_type,
                "reference_name": ref_name, "description": desc,
                "priority": "Medium", "modified": "",
            })
        finally:
            frappe.db.get_value = orig

    def test_no_first_class_source_opens_the_todo_list(self):
        """Every first-class source (approval / WTU / PM Task) must open its
        canonical business destination -- NEVER the Desk ToDo list."""
        cases = [
            ("GBS Purchase Order", "GBS-PO-1"),   # approval
            ("Weekly Team Update", "WTU-1"),      # weekly update
            ("Task", "TASK-1"),                   # PM task
        ]
        for rt, rn in cases:
            url = self._resolve(rt, rn)["action_url"]
            # Never the list view, and never a bare /app/todo path.
            self.assertNotIn("/app/todo", url, "%s -> %s" % (rt, url))
            self.assertNotIn("todo/view/list", url, "%s -> %s" % (rt, url))

    def test_each_source_opens_its_canonical_route(self):
        self.assertTrue(
            self._resolve("SO Request", "SO-1")["action_url"].startswith("/approval?"))
        self.assertTrue(
            self._resolve("Weekly Team Update", "WTU-1")["action_url"].startswith("/weekly-update?week="))
        self.assertTrue(
            self._resolve("Task", "TASK-1")["action_url"].startswith("/pm#task/"))

    def test_permission_safe_first_class_urls_are_portal_not_desk(self):
        """Portal routes (/approval, /weekly-update, /pm) are reachable by
        internal website users; Desk (/app/*) is not guaranteed. First-class
        sources must resolve to portal routes."""
        for rt, rn in (("MSO Request", "MSO-1"), ("Weekly Team Update", "WTU-1"),
                       ("Task", "TASK-1")):
            url = self._resolve(rt, rn)["action_url"]
            self.assertFalse(url.startswith("/app/"), "%s -> %s" % (rt, url))

    def test_generic_todo_fallbacks(self):
        # Referenced doc valid -> Desk referenced document (not the list).
        u1 = self._resolve("Mystery Doc", "MYS-001")["action_url"]
        self.assertEqual(u1, "/app/mystery-doc/MYS-001")
        self.assertNotIn("todo/view/list", u1)
        # Bare ToDo (no reference) -> the specific ToDo doc, ToDo fallback ONLY
        # (a single document, never the list view).
        u2 = self._resolve("", "", name="todo-9")["action_url"]
        self.assertEqual(u2, "/app/todo/todo-9")
        self.assertNotIn("todo/view/list", u2)

    def test_unknown_doctype_uses_desk_fallback_with_dashes(self):
        orig = frappe.db.get_value
        frappe.db.get_value = lambda *a, **kw: None
        try:
            item = resolvers.resolve_item({
                "name": "todo-4", "reference_type": "Mystery Doc",
                "reference_name": "MYS-001",
                "description": "x", "priority": "Low", "modified": "",
            })
            self.assertEqual(item["source_key"], "generic")
            self.assertEqual(item["action_url"], "/app/mystery-doc/MYS-001")
            self.assertNotIn("/approval", item["action_url"])
        finally:
            frappe.db.get_value = orig

    def test_no_reference_type_links_to_todo_desk(self):
        item = resolvers.resolve_item({
            "name": "todo-5", "reference_type": "", "reference_name": "",
            "description": "Ad-hoc", "priority": "Medium", "modified": "",
        })
        self.assertEqual(item["source_key"], "generic")
        self.assertEqual(item["action_url"], "/app/todo/todo-5")
        self.assertNotIn("/approval", item["action_url"])


class _FakeDocField(dict):
    """Minimal stand-in for a Frappe DocField (dict-like + .fieldtype attr)."""

    @property
    def fieldtype(self):
        return self.get("fieldtype")


class _FakeMeta:
    """Stand-in for frappe.get_meta(dt): knows its title_field + fields."""

    def __init__(self, title_field, fields):
        self._title_field = title_field
        self._fields = {f["fieldname"]: f for f in fields}

    def get_title_field(self):
        return self._title_field or "name"

    def has_field(self, fn):
        return fn in self._fields

    def get_field(self, fn):
        f = self._fields.get(fn)
        return _FakeDocField(f) if f else None


class TestActionCenterTitleResolution(FrappeTestCase):
    """resolve_title must be metadata-driven: it may only SELECT columns that
    physically exist, so a DocType without a `title` column can never trigger
    MySQL 1054 (Unknown column). Hotfix for the hard-coded ["title","name"]
    query that assumed every referenced DocType has a physical `title` column.

    The fake DB below emulates MySQL 1054: selecting a column that is not a
    physical column raises -- exactly as the real database would. So any test
    that resolves without raising proves no invalid SQL was issued."""

    #: doctype -> (title_field, declared docfields, physical columns)
    SCHEMA = {
        # title_field="subject"; subject is a real Data column.
        "Leave Application": ("subject",
            [{"fieldname": "subject", "fieldtype": "Data"}],
            {"name", "subject"}),
        # no title_field configured -> get_title_field() returns "name".
        "PO Request": ("",
            [{"fieldname": "amount", "fieldtype": "Currency"}],
            {"name", "amount"}),
        # title_field points at a field with NO physical column (virtual/misconfig).
        "SO Request": ("headline",
            [{"fieldname": "headline", "fieldtype": "Data", "is_virtual": 1}],
            {"name"}),
        # title_field points at a real column.
        "MSO Request": ("request_title",
            [{"fieldname": "request_title", "fieldtype": "Data"}],
            {"name", "request_title"}),
    }

    RECORDS = {
        ("Leave Application", "LEAVE-1"): {"name": "LEAVE-1", "subject": "Annual leave"},
        ("PO Request", "PO-1"): {"name": "PO-1", "amount": 100},
        ("SO Request", "SO-1"): {"name": "SO-1"},
        ("MSO Request", "MSO-1"): {"name": "MSO-1", "request_title": "Brand X May"},
        # ("MSO Request", "MSO-GONE") deliberately absent -> get_value None.
    }

    def _reset_title_cache(self):
        # Request-scoped cache lives on frappe.local; drop it so each test
        # starts with a clean per-request cache.
        if hasattr(frappe.local, resolvers._TITLE_FIELD_LOCAL_ATTR):
            delattr(frappe.local, resolvers._TITLE_FIELD_LOCAL_ATTR)

    def setUp(self):
        self._reset_title_cache()
        self._orig_meta = frappe.get_meta
        self._orig_gv = frappe.db.get_value
        self.select_log = []
        frappe.get_meta = self._fake_meta
        frappe.db.get_value = self._fake_get_value

    def tearDown(self):
        frappe.get_meta = self._orig_meta
        frappe.db.get_value = self._orig_gv
        self._reset_title_cache()

    def _fake_meta(self, dt):
        tf, fields, _cols = self.SCHEMA[dt]
        return _FakeMeta(tf, fields)

    def _fake_get_value(self, dt, name, fields, as_dict=False, **kw):
        _tf, _fields, cols = self.SCHEMA[dt]
        req = list(fields) if isinstance(fields, (list, tuple)) else [fields]
        self.select_log.append((dt, tuple(req)))
        for c in req:
            if c not in cols:
                raise Exception("(1054, \"Unknown column '%s' in 'field list'\")" % c)
        rec = self.RECORDS.get((dt, name))
        if rec is None:
            return None
        return {c: rec.get(c) for c in req} if as_dict else [rec.get(c) for c in req]

    def _selected_columns(self):
        return [c for _dt, cols in self.select_log for c in cols]

    def test_title_field_subject_used(self):
        # DocType with title_field="subject" -> uses subject.
        self.assertEqual(
            resolvers.resolve_title("Leave Application", "LEAVE-1"), "Annual leave")

    def test_no_title_field_uses_name(self):
        # DocType without title_field -> uses name; never SELECTs `title`.
        self.assertEqual(resolvers.resolve_title("PO Request", "PO-1"), "PO-1")
        self.assertNotIn("title", self._selected_columns())

    def test_title_field_missing_physical_column_no_invalid_sql(self):
        # title_field missing physically -> no invalid SQL; falls back to name.
        title = resolvers.resolve_title("SO Request", "SO-1")   # must not raise
        self.assertEqual(title, "SO-1")
        self.assertNotIn("headline", self._selected_columns())
        self.assertNotIn("title", self._selected_columns())

    def test_missing_record_safe_fallback(self):
        # Referenced record missing -> get_value None -> fall back to ref name.
        self.assertEqual(resolvers.resolve_title("MSO Request", "MSO-GONE"), "MSO-GONE")

    def test_mixed_feed_of_many_doctypes_no_exception(self):
        # Mixed feed of many DocTypes (some without a `title` column) -> no exception.
        for dt, nm in (("Leave Application", "LEAVE-1"), ("PO Request", "PO-1"),
                       ("SO Request", "SO-1"), ("MSO Request", "MSO-1"),
                       ("MSO Request", "MSO-GONE")):
            resolvers.resolve_title(dt, nm)   # no raise
        self.assertNotIn("title", self._selected_columns())

    def test_title_field_resolution_cached_per_doctype(self):
        # Metadata resolved once per DocType even across many feed rows.
        calls = {"n": 0}
        base = self._fake_meta

        def counting_meta(dt):
            calls["n"] += 1
            return base(dt)

        frappe.get_meta = counting_meta
        for _ in range(5):
            resolvers.resolve_title("MSO Request", "MSO-1")
        self.assertEqual(calls["n"], 1)   # 5 rows -> 1 get_meta

    def test_resolve_item_approval_branch_uses_metadata_title(self):
        # End-to-end: the approval branch of resolve_item now resolves the title
        # via metadata (title_field) instead of a hard-coded ["title","name"].
        item = resolvers.resolve_item({
            "name": "todo-t", "reference_type": "Leave Application",
            "reference_name": "LEAVE-1", "description": "x",
            "priority": "Medium", "modified": "",
        })
        self.assertEqual(item["title"], "Annual leave")
        self.assertNotIn("title", self._selected_columns())
