# Copyright (c) 2026, eCentric and contributors
"""Notification Center foundation tests (site-free; self-stubbed frappe).

Covers the N1 security + behaviour contract:
  * user A never sees / marks user B's notifications
  * unread count is per-user and correct
  * mark_read is idempotent and ownership-checked
  * mark_all_read only affects the current user
  * the Weekly Update action_url is built by the shared resolver (no frontend route)
  * the realtime payload is scoped to the recipient (no other user's data)
  * the homepage bell patch is idempotent and fail-loud
  * the frontend asset escapes output and never builds routes

    bench run-tests --module ecentric_workspace.notification_center.tests.test_notification_center
"""
import os
import sys
import types
import unittest


# --------------------------------------------------------------------------- #
# Self-contained frappe stub (installed once; reset per test).
# --------------------------------------------------------------------------- #
def _install_frappe():
    if "frappe" in sys.modules:
        return sys.modules["frappe"]
    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user="a@x.com")
    fr.response = {}
    fr.flags = types.SimpleNamespace()
    fr.ValidationError = type("ValidationError", (Exception,), {})
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr._ = lambda s: s
    fr.log_error = lambda *a, **k: None
    fr.get_traceback = lambda *a, **k: ""
    fr.clear_cache = lambda *a, **k: None
    fr.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
    fr._nl = []           # Notification Log store (list of dicts)
    fr._seq = [0]
    fr._docs = {}         # (doctype, name) -> field dict (for get_value)
    fr._realtime = []     # captured publish_realtime calls
    fr._webpages = {}     # name -> {route, main_section, main_section_html}

    def _nl_by_name(name):
        for r in fr._nl:
            if r.get("name") == name:
                return r
        return None

    # ---- frappe.db ----
    db = types.SimpleNamespace()

    def get_all(doctype, filters=None, fields=None, order_by=None,
                limit_page_length=None, **k):
        filters = filters or {}
        if doctype == "Notification Log":
            rows = [r for r in fr._nl if all(r.get(kk) == vv for kk, vv in filters.items())]
            rows = sorted(rows, key=lambda r: r.get("creation") or "", reverse=True)
            if limit_page_length:
                rows = rows[:int(limit_page_length)]
            if fields:
                rows = [{f: r.get(f) for f in fields} for r in rows]
            return [dict(r) for r in rows]
        if doctype == "Web Page":
            out = []
            for nm, wp in fr._webpages.items():
                if all(wp.get(kk) == vv for kk, vv in filters.items()):
                    out.append({"name": nm})
            return out[:int(limit_page_length or 99)]
        return []

    def count(doctype, filters=None):
        filters = filters or {}
        if doctype == "Notification Log":
            return sum(1 for r in fr._nl if all(r.get(kk) == vv for kk, vv in filters.items()))
        return 0

    def get_value(doctype, name, field=None, as_dict=False):
        if doctype == "Notification Log":
            row = _nl_by_name(name) or {}
            if field == "for_user":
                return row.get("for_user")
        rec = fr._docs.get((doctype, name), {})
        if as_dict:
            keys = field if isinstance(field, (list, tuple)) else [field]
            return {f: rec.get(f) for f in keys}
        if isinstance(field, (list, tuple)):
            return [rec.get(f) for f in field]
        return rec.get(field)

    def set_value(doctype, name, field, value):
        if doctype == "Notification Log":
            row = _nl_by_name(name)
            if row is not None:
                row[field] = value

    def sql(query, params=None):
        q = " ".join(query.split()).lower()
        if "update `tabnotification log` set `read`=1" in q and "for_user=%s" in q:
            user = params if isinstance(params, str) else params[0]
            for r in fr._nl:
                if r.get("for_user") == user:
                    r["read"] = 1
        return []

    db.get_all = get_all
    db.count = count
    db.get_value = get_value
    db.set_value = set_value
    db.sql = sql
    db.exists = lambda doctype, name: (doctype == "Web Page" and name in fr._webpages)
    db.commit = lambda: None
    fr.db = db
    fr.get_all = get_all

    # ---- frappe.get_doc (dict -> insert new; (doctype,name) -> fetch Web Page) ----
    class _NLDoc(dict):
        def insert(self, ignore_permissions=False):
            fr._seq[0] += 1
            self["name"] = "NL-%05d" % fr._seq[0]
            self["creation"] = "2026-06-22 09:00:0%d" % (fr._seq[0] % 10)
            self.setdefault("read", 0)
            self.name = self["name"]
            self.creation = self["creation"]
            fr._nl.append(dict(self))
            return self

    class _WPDoc:
        def __init__(self, name, data):
            self._name = name
            self.main_section = data.get("main_section")
            self.main_section_html = data.get("main_section_html")

        def save(self, ignore_permissions=False):
            fr._webpages[self._name]["main_section"] = self.main_section
            fr._webpages[self._name]["main_section_html"] = self.main_section_html

    def get_doc(arg, name=None):
        if isinstance(arg, dict):
            return _NLDoc(arg)
        if arg == "Web Page":
            return _WPDoc(name, fr._webpages[name])
        raise Exception("unexpected get_doc(%r,%r)" % (arg, name))

    fr.get_doc = get_doc
    fr.publish_realtime = lambda **kw: fr._realtime.append(kw)
    fr.utils = types.SimpleNamespace(
        format_datetime=lambda *a, **k: "Thu 25/06/2026 17:00")
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fr.utils
    return fr


FR = _install_frappe()

from ecentric_workspace.notification_center import api  # noqa: E402
from ecentric_workspace.notification_center import service as svc  # noqa: E402
from ecentric_workspace.notification_center import resolvers as res  # noqa: E402


def _add(name, for_user, read=0, subject="s", dtype="", dname="", from_user="sys",
         creation="2026-06-22 09:00:00"):
    FR._nl.append({"name": name, "for_user": for_user, "read": read, "subject": subject,
                   "email_content": "m", "document_type": dtype, "document_name": dname,
                   "from_user": from_user, "type": "Alert", "creation": creation})


def _reset(user="a@x.com"):
    FR._nl[:] = []
    FR._docs.clear()
    FR._realtime[:] = []
    FR._webpages.clear()
    FR.response.clear()
    FR.session.user = user


class TestApiScope(unittest.TestCase):
    def setUp(self):
        _reset("a@x.com")
        _add("N1", "a@x.com", read=0)
        _add("N2", "a@x.com", read=1)
        _add("N3", "b@x.com", read=0)        # belongs to another user

    def test_user_only_sees_own(self):
        res_a = api.get_notifications()
        names = {i["name"] for i in res_a["items"]}
        self.assertEqual(names, {"N1", "N2"})
        self.assertNotIn("N3", names)

    def test_unread_count_per_user(self):
        self.assertEqual(api.get_unread_count()["unread"], 1)   # only N1
        FR.session.user = "b@x.com"
        self.assertEqual(api.get_unread_count()["unread"], 1)   # only N3

    def test_cannot_mark_other_users(self):
        r = api.mark_read(notification_name="N3")               # A marking B's row
        self.assertFalse(r["success"])
        self.assertEqual(FR._nl[2]["read"], 0)                  # N3 untouched

    def test_mark_read_idempotent_and_owned(self):
        self.assertTrue(api.mark_read(notification_name="N1")["success"])
        self.assertEqual(FR._nl[0]["read"], 1)
        self.assertTrue(api.mark_read(notification_name="N1")["success"])   # again: no error
        self.assertEqual(FR._nl[0]["read"], 1)

    def test_mark_all_read_only_current_user(self):
        api.mark_all_read()
        self.assertEqual(FR._nl[0]["read"], 1)   # a's N1 now read
        self.assertEqual(FR._nl[1]["read"], 1)   # a's N2 stays read
        self.assertEqual(FR._nl[2]["read"], 0)   # b's N3 NOT touched

    def test_guest_unauthorized(self):
        FR.session.user = "Guest"
        out = api.get_notifications()
        self.assertFalse(out["success"])
        self.assertEqual(FR.response.get("http_status_code"), 401)

    def test_items_have_canonical_shape(self):
        item = api.get_notifications()["items"][0]
        for key in ("name", "subject", "message", "source_type", "source_label",
                    "action_url", "is_read", "created_at", "from_user"):
            self.assertIn(key, item)


class TestResolver(unittest.TestCase):
    def setUp(self):
        _reset()
        FR._docs[("Weekly Team Update", "WTU-1")] = {"week_label": "2026-W26", "status": "Draft"}

    def test_weekly_update_action_url(self):
        item = res.resolve_notification({
            "name": "N", "subject": "s", "email_content": "m",
            "document_type": "Weekly Team Update", "document_name": "WTU-1",
            "from_user": "sys", "read": 0, "type": "Alert", "creation": "x"})
        self.assertEqual(item["action_url"], "/weekly-update?week=2026-W26")
        self.assertEqual(item["source_type"], "weekly_report")

    def test_no_reference_no_url(self):
        item = res.resolve_notification({"name": "N", "subject": "s", "email_content": "",
                                         "document_type": "", "document_name": ""})
        self.assertEqual(item["action_url"], "")

    def test_unknown_doctype_desk_fallback(self):
        item = res.resolve_notification({"name": "N", "subject": "s",
                                         "document_type": "Lead", "document_name": "LEAD-9"})
        self.assertEqual(item["action_url"], "/app/lead/LEAD-9")


class TestServiceEmit(unittest.TestCase):
    def setUp(self):
        _reset()
        FR._docs[("Weekly Team Update", "WTU-1")] = {"week_label": "2026-W26", "status": "Draft"}
        FR._docs[("Weekly Team Update", "WTU-DONE")] = {"week_label": "2026-W25", "status": "Submitted"}

    def test_emit_creates_log_and_scoped_realtime(self):
        name = svc.emit("a@x.com", "Hi", "body", document_type="Weekly Team Update",
                        document_name="WTU-1", from_user="Administrator")
        self.assertTrue(name)
        self.assertEqual(len(FR._nl), 1)
        self.assertEqual(FR._nl[0]["for_user"], "a@x.com")
        # exactly one realtime ping, delivered to the recipient only.
        self.assertEqual(len(FR._realtime), 1)
        ping = FR._realtime[0]
        self.assertEqual(ping["user"], "a@x.com")
        self.assertEqual(ping["event"], "ec_notification")
        # payload carries ONLY the recipient's own item + their unread count.
        self.assertEqual(set(ping["message"].keys()), {"item", "unread"})
        self.assertEqual(ping["message"]["item"]["name"], name)
        self.assertEqual(ping["message"]["unread"], 1)

    def test_pilot_skips_terminal_wtu(self):
        out = svc.notify_weekly_update_created("WTU-DONE", "a@x.com", "2026-W25", "due")
        self.assertIsNone(out)
        self.assertEqual(FR._nl, [])               # nothing emitted for Submitted WTU

    def test_pilot_emits_for_draft_wtu(self):
        out = svc.notify_weekly_update_created("WTU-1", "a@x.com", "2026-W26", "Thu 25/06")
        self.assertTrue(out)
        self.assertEqual(FR._nl[0]["document_type"], "Weekly Team Update")
        self.assertIn("2026-W26", FR._nl[0]["subject"])


class TestPatch(unittest.TestCase):
    def setUp(self):
        _reset()
        from ecentric_workspace.notification_center.patches import p001_homepage_notification_bell as p
        self.p = p
        self.ANCHOR = p.ANCHOR
        self.MARKER = p.BELL_MARKER

    def _wp(self, body):
        FR._webpages["ecentric-workspace"] = {"route": "home",
                                              "main_section": body, "main_section_html": body}

    def test_insert_after_anchor_idempotent(self):
        body = "<div>x</div>" + self.ANCHOR + "<div>y</div>"
        self._wp(body)
        self.p.execute()
        out = FR._webpages["ecentric-workspace"]["main_section"]
        self.assertIn(self.MARKER, out)
        self.assertEqual(out.count(self.MARKER), 1)
        # idempotent: second run is a no-op (still exactly one marker).
        self.p.execute()
        out2 = FR._webpages["ecentric-workspace"]["main_section"]
        self.assertEqual(out2.count(self.MARKER), 1)

    def test_fail_loud_without_anchor(self):
        self._wp("<div>no anchor here</div>")
        with self.assertRaises(FR.ValidationError):
            self.p.execute()

    def test_fail_loud_on_unknown_field_state(self):
        # one field has the anchor, the other is unknown -> refuse to mutate.
        FR._webpages["ecentric-workspace"] = {
            "route": "home",
            "main_section": "x" + self.ANCHOR,
            "main_section_html": "totally different unexpected content"}
        with self.assertRaises(FR.ValidationError):
            self.p.execute()


class TestAssetContract(unittest.TestCase):
    """Static guards on the frontend asset: no route building, output is escaped."""
    def setUp(self):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(here, "public", "js", "notification_center.js"),
                  encoding="utf-8") as fh:
            self.js = fh.read()

    def test_uses_server_action_url_not_route_building(self):
        self.assertIn("it.action_url", self.js)
        # must NOT hand-build the weekly-update (or any) route on the client.
        self.assertNotIn("/weekly-update?week=", self.js)
        self.assertNotIn("'/weekly-update'", self.js)

    def test_escapes_output(self):
        self.assertIn("function esc(", self.js)
        for token in ("esc(it.subject", "esc(it.message", "esc(it.source_label"):
            self.assertIn(token, self.js)

    def test_sound_respects_mute_and_interaction(self):
        self.assertIn("if (isMuted() || !S.interacted) return;", self.js)

    def test_calls_only_notification_center_api(self):
        self.assertIn("ecentric_workspace.notification_center.api.", self.js)


def _pkg_root():
    # .../notification_center/tests/<file> -> .../  (the inner ecentric_workspace package)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    with open(os.path.join(_pkg_root(), *parts), encoding="utf-8") as fh:
        return fh.read()


class TestMethodContract(unittest.TestCase):
    """Lock the GET/POST contract end to end so the Action Center 403 method-mismatch
    cannot recur: backend decorators AND the frontend frappe.call type must agree."""

    def setUp(self):
        self.api_src = _read("notification_center", "api.py")
        self.js = _read("public", "js", "notification_center.js")

    def test_backend_get_endpoints(self):
        for fn in ("get_notifications", "get_unread_count"):
            self.assertIn('@frappe.whitelist(methods=["GET"])\ndef ' + fn, self.api_src,
                          fn + " must be a GET endpoint")

    def test_backend_post_endpoints(self):
        for fn in ("mark_read", "mark_all_read"):
            self.assertIn('@frappe.whitelist(methods=["POST"])\ndef ' + fn, self.api_src,
                          fn + " must be a POST endpoint")

    def test_frontend_get_calls(self):
        self.assertIn("call('get_notifications', 'GET'", self.js)
        self.assertIn("call('get_unread_count', 'GET'", self.js)
        # GET endpoints must never be called with POST (the actual 403 cause).
        self.assertNotIn("call('get_notifications', 'POST'", self.js)
        self.assertNotIn("call('get_unread_count', 'POST'", self.js)

    def test_frontend_post_calls(self):
        self.assertIn("call('mark_read', 'POST'", self.js)
        self.assertIn("call('mark_all_read', 'POST'", self.js)

    def test_frontend_forwards_explicit_type(self):
        self.assertIn("type: httpType", self.js)


class TestAdditionalGuards(unittest.TestCase):
    def setUp(self):
        _reset()
        self.js = _read("public", "js", "notification_center.js")
        self.svc_src = _read("notification_center", "service.py")

    def test_patch_registered_after_action_center(self):
        lines = _read("patches.txt").splitlines()
        ac = [i for i, l in enumerate(lines)
              if "action_center.patches.p001_homepage_action_center" in l]
        nc = [i for i, l in enumerate(lines)
              if "notification_center.patches.p001_homepage_notification_bell" in l]
        self.assertTrue(ac and nc, "both patch entries must be present")
        self.assertGreater(nc[0], ac[0], "bell patch must run AFTER action_center patch")

    def test_action_url_is_relative_same_origin(self):
        FR._docs[("Weekly Team Update", "WTU-1")] = {"week_label": "2026-W26"}
        cases = [("Weekly Team Update", "WTU-1"), ("Task", "T-1"),
                 ("Sales Order", "SO-1"), ("Lead", "L-1"), ("", "")]
        for dt, dn in cases:
            item = res.resolve_notification({"document_type": dt, "document_name": dn,
                                             "subject": "s"})
            u = item["action_url"]
            if u:
                self.assertTrue(u.startswith("/"), (dt, u))
                self.assertFalse(u.startswith("//"), (dt, u))
                self.assertNotIn("://", u, (dt, u))

    def test_emit_uses_after_commit(self):
        self.assertIn("after_commit=True", self.svc_src,
                      "realtime must publish only after commit")

    def test_frontend_href_uses_action_url_not_content(self):
        # the link target is the server action_url; never the raw subject/message.
        self.assertIn("esc(it.action_url", self.js)
        self.assertNotIn("href=\"' + esc(it.message", self.js)
        self.assertNotIn("href=\"' + esc(it.subject", self.js)

    def test_single_install_guard(self):
        # re-running the asset must not stack pollers/handlers.
        self.assertIn("if (window._ecNotifCenterInstalled) { return; }", self.js)


class TestSingleBell(unittest.TestCase):
    """Single-bell hotfix: the asset must REUSE the native header bell and never render
    a second/custom bell."""

    def setUp(self):
        self.js = _read("public", "js", "notification_center.js")

    def test_reuses_native_bell_selector(self):
        self.assertIn("function findBell", self.js)
        self.assertIn(".topbar-actions a.icon-btn", self.js)
        self.assertIn("notification-log", self.js)

    def test_no_custom_or_emoji_bell(self):
        # no second clickable bell, no floating yellow circle, no emoji glyph bell.
        self.assertNotIn('id="ec-nc-bell"', self.js)
        self.assertNotIn("#ec-nc-bell", self.js)
        self.assertNotIn("1F514", self.js)            # the old \u{1F514} bell emoji
        self.assertNotIn("position:fixed;top:14px", self.js)

    def test_badge_attached_to_native_bell(self):
        # the live count badge is appended to the native bell; the static .dot is hidden.
        self.assertIn("bell.appendChild(badgeEl)", self.js)
        self.assertIn("bell.querySelector('.dot')", self.js)
        self.assertIn("'9+'", self.js)                # capped count -> no header shift

    def test_footer_actions_only(self):
        self.assertIn("Đánh dấu tất cả đã đọc", self.js)
        self.assertIn("Xem tất cả thông báo", self.js)
        self.assertIn('href="/app/notification-log"', self.js)

    def test_dismissal_and_keyboard(self):
        self.assertIn("'Escape'", self.js)
        self.assertIn("!pop.contains(ev.target) && !bell.contains(ev.target)", self.js)
        self.assertIn("tabindex=", self.js)

    def test_only_plain_left_click_is_intercepted(self):
        # Ctrl/Cmd/Shift/Alt/middle-click keep the native /app/notification-log behaviour.
        self.assertIn("ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey",
                      self.js)



class TestGlobalShellLoader(unittest.TestCase):
    """Global shell loader: the NC asset must load on EVERY website-rendered eCentric
    page via a single shared hook (web_include_js), never per-page, and never on Frappe
    Desk. Old per-page \'Tính năng đang phát triển\' handler must be neutralised."""

    def setUp(self):
        self.hooks = _read("hooks.py")
        self.js = _read("public", "js", "notification_center.js")

    # ---- single shared global loader point ----
    def test_web_include_js_registers_asset_globally(self):
        self.assertIn(
            'web_include_js = ["/assets/ecentric_workspace/js/notification_center.js"]',
            self.hooks,
            "asset must be registered as a global website include (one shared point)")

    def test_not_bound_to_frappe_desk_app_include(self):
        # app_include_js would load into Frappe Desk (/app) and bind its native bell;
        # there must be no such assignment (a comment mentioning it is fine).
        self.assertNotIn("app_include_js =", self.hooks)

    def test_asset_has_precise_desk_guard(self):
        # bails ONLY on the real Desk root (/app or /app/...), never on lookalike
        # website routes such as /approval (Phê duyệt) or /app-... .
        self.assertIn("_p === '/app'", self.js)
        self.assertIn("_p.indexOf('/app/') === 0", self.js)
        # the naive guard (which would also kill /approval) must be gone.
        self.assertNotIn(".indexOf('/app') === 0", self.js)

    def test_no_per_page_patch_created(self):
        # The global loader must NOT be implemented as a DB patch per page. The only
        # notification_center patches are the original homepage p001 and the SINGLE
        # architecture-migration cleanup p002 (homepage-only -> global). No more.
        pdir = os.path.join(_pkg_root(), "notification_center", "patches")
        pyfiles = sorted(f for f in os.listdir(pdir)
                         if f.endswith(".py") and f != "__init__.py")
        self.assertEqual(pyfiles, [
            "p001_homepage_notification_bell.py",
            "p002_retire_homepage_bell_loader.py",
        ])

    # ---- badge redesign ----
    def test_badge_hidden_when_zero(self):
        self.assertIn("S.unread > 0", self.js)
        self.assertIn("badgeEl.classList.remove('on')", self.js)

    def test_badge_circle_and_capped_pill(self):
        self.assertIn("ec-nc-badge--pill", self.js)      # 9+ pill variant
        self.assertIn("'9+'", self.js)                   # capped, no header shift
        self.assertIn("S.unread > 9", self.js)

    def test_badge_uses_existing_token_white_ring_not_yellow_not_square(self):
        self.assertIn("background:var(--pink", self.js)  # existing color token
        self.assertIn("border:2px solid #fff", self.js)  # ~2px white ring
        self.assertIn("border-radius:8px", self.js)      # rounded -> not a square box
        self.assertIn("font-weight:600", self.js)        # semibold
        self.assertNotIn("yellow", self.js.lower())      # no custom yellow

    def test_badge_anchored_top_right_absolute(self):
        # absolute placement at the bell corner -> never shifts the header
        self.assertIn(".ec-nc-badge{position:absolute", self.js)
        self.assertIn("top:-4px;right:-4px", self.js)

    # ---- single badge / single dropdown (no duplicates on re-render) ----
    def test_single_badge_idempotent_mount(self):
        self.assertIn("bell.querySelector('.ec-nc-badge')", self.js)
        self.assertIn("prev.parentNode.removeChild(prev)", self.js)

    def test_single_dropdown_idempotent_build(self):
        self.assertIn("getElementById('ec-nc-pop-root')", self.js)

    def test_reinstall_guard_sets_flag(self):
        self.assertIn("if (window._ecNotifCenterInstalled) { return; }", self.js)
        self.assertIn("window._ecNotifCenterInstalled = true;", self.js)

    # ---- legacy handler neutralised (no DB edit) ----
    def test_legacy_handler_stripped_on_adopt(self):
        self.assertIn("function adoptBell", self.js)
        self.assertIn("cloneNode(true)", self.js)
        self.assertIn("replaceChild(clone, orig)", self.js)
        self.assertIn("removeAttribute('onclick')", self.js)
        self.assertIn("ev.stopPropagation();", self.js)

    def test_asset_does_not_contain_legacy_message(self):
        self.assertNotIn("đang phát triển", self.js)

    def test_modified_clicks_still_open_native(self):
        # Ctrl/Cmd/Shift/Alt/middle-click fall through to /app/notification-log.
        self.assertIn("ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey",
                      self.js)


class TestDomRuntime(unittest.TestCase):
    """Execute the real asset against a DOM/frappe stub (node) to prove the runtime
    badge matrix, single badge/dropdown, reinstall-no-duplicate, Desk guard and
    legacy-handler stripping. Skipped automatically where node is unavailable."""

    def test_dom_runtime_behaviour(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        for harness_name in ("dom_runtime_check.js", "bell_click_check.js"):
            harness = os.path.join(_pkg_root(), "notification_center", "tests",
                                   harness_name)
            proc = subprocess.run([node, harness], capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0,
                             harness_name + " assertions failed:\n" + proc.stdout + proc.stderr)



class TestRetireHomepageLoaderPatch(unittest.TestCase):
    """p002 retires the homepage-only NC <script> (now redundant under the global
    web_include_js loader) so /home loads the asset exactly once -- WITHOUT touching
    Action Center, and idempotently (the p001 script already ran in production)."""

    BELL_LOADER = (
        '<script id="ec-notification-center" '
        'src="/assets/ecentric_workspace/js/notification_center.js" '
        'defer></script><!-- /ec-notification-center -->')
    AC = "<!-- /ec-action-center-widget -->"

    def setUp(self):
        _reset()
        from ecentric_workspace.notification_center.patches import (
            p002_retire_homepage_bell_loader as p)
        self.p = p

    def _wp(self, body):
        FR._webpages["ecentric-workspace"] = {
            "route": "home", "main_section": body, "main_section_html": body}

    def test_removes_bell_loader_idempotent(self):
        body = "<div>AC widget</div>" + self.AC + self.BELL_LOADER + "<div>tail</div>"
        self._wp(body)
        self.p.execute()
        out = FR._webpages["ecentric-workspace"]["main_section"]
        self.assertNotIn('<script id="ec-notification-center"', out)
        self.assertIn(self.AC, out)                       # Action Center untouched
        self.assertIn("<div>AC widget</div>", out)
        self.assertIn("<div>tail</div>", out)
        # second run is a clean no-op (still no bell loader, AC intact).
        self.p.execute()
        out2 = FR._webpages["ecentric-workspace"]["main_section"]
        self.assertNotIn('<script id="ec-notification-center"', out2)
        self.assertIn(self.AC, out2)

    def test_noop_when_loader_absent(self):
        body = "<div>AC widget</div>" + self.AC + "<div>tail</div>"
        self._wp(body)
        self.p.execute()
        out = FR._webpages["ecentric-workspace"]["main_section"]
        self.assertEqual(out, body)                       # nothing changed

    def test_action_center_anchor_count_preserved(self):
        body = self.AC + self.BELL_LOADER + self.AC       # two AC anchors
        self._wp(body)
        self.p.execute()
        out = FR._webpages["ecentric-workspace"]["main_section"]
        self.assertEqual(out.count(self.AC), 2)
        self.assertNotIn('<script id="ec-notification-center"', out)

    def test_registered_after_p001(self):
        lines = _read("patches.txt").splitlines()
        p1 = [i for i, l in enumerate(lines)
              if "notification_center.patches.p001_homepage_notification_bell" in l]
        p2 = [i for i, l in enumerate(lines)
              if "notification_center.patches.p002_retire_homepage_bell_loader" in l]
        self.assertTrue(p1 and p2, "both NC patch entries must be present")
        self.assertGreater(p2[0], p1[0], "p002 must run AFTER p001")


if __name__ == "__main__":
    unittest.main()
