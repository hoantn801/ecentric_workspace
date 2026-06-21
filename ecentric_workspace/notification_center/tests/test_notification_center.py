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
    fr._delivery = []     # EC Notification Delivery Log store (live doc objects)
    fr._prefs = {}        # user -> EC Notification Preference doc object
    fr._enqueued = []     # captured frappe.enqueue calls
    fr._conf = {}         # site_config stub (frappe.get_conf)
    fr._tasks = {}        # Task store (name -> dict)
    fr._wtus = {}         # Weekly Team Update store (name -> dict)
    fr._roles = []        # frappe.get_roles()
    fr._mail = []         # frappe.sendmail captures

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
        if doctype in ("Task", "Weekly Team Update"):
            store = fr._tasks if doctype == "Task" else fr._wtus
            def _norm(v):
                return "" if v is None else str(v)
            def _mt(r):
                for kk, vv in (filters or {}).items():
                    rv = r.get(kk)
                    if isinstance(vv, (list, tuple)) and len(vv) == 2 and vv[0] in (
                            "<", "<=", ">", ">=", "in", "not in", "between", "like"):
                        op, val = vv
                        if op == "<" and not (_norm(rv) < _norm(val)):
                            return False
                        if op == "<=" and not (_norm(rv) <= _norm(val)):
                            return False
                        if op == ">" and not (_norm(rv) > _norm(val)):
                            return False
                        if op == ">=" and not (_norm(rv) >= _norm(val)):
                            return False
                        if op == "in" and rv not in val:
                            return False
                        if op == "not in" and rv in val:
                            return False
                        if op == "between" and not (_norm(val[0]) <= _norm(rv) <= _norm(val[1])):
                            return False
                        if op == "like" and str(val).strip("%") not in _norm(rv):
                            return False
                    elif rv != vv:
                        return False
                return True
            rows = [dict(r, name=nm) for nm, r in store.items() if _mt(dict(r, name=nm))]
            if fields:
                rows = [{f: r.get(f) for f in fields} for r in rows]
            return rows
        if doctype == "EC Notification Delivery Log":
            def _match(r):
                for kk, vv in filters.items():
                    rv = r.get(kk)
                    if isinstance(vv, (list, tuple)) and len(vv) == 2:
                        op, val = vv
                        if op == "<=" and not (rv is not None and rv <= val):
                            return False
                        if op == "<" and not (rv is not None and rv < val):
                            return False
                        if op == ">=" and not (rv is not None and rv >= val):
                            return False
                    elif rv != vv:
                        return False
                return True
            rows = [r for r in fr._delivery if _match(r)]
            lim = k.get("limit")
            if lim:
                rows = rows[:int(lim)]
            if k.get("pluck"):
                return [r.get(k["pluck"]) for r in rows]
            if fields:
                return [{f: r.get(f) for f in fields} for r in rows]
            return [dict(r) for r in rows]
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
        if doctype == "Task":
            rec = fr._tasks.get(name) or fr._docs.get((doctype, name), {})
            if isinstance(field, (list, tuple)):
                return [rec.get(f) for f in field]
            return rec.get(field)
        if doctype == "Weekly Team Update":
            rec = fr._wtus.get(name) or fr._docs.get((doctype, name), {})
            if isinstance(field, (list, tuple)):
                return [rec.get(f) for f in field]
            return rec.get(field)
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
    def _exists(doctype, name):
        if doctype == "Web Page":
            return name in fr._webpages
        if doctype == "EC Notification Preference":
            return name in fr._prefs
        if doctype == "EC Notification Delivery Log":
            if isinstance(name, dict):
                for r in fr._delivery:
                    if all(r.get(k) == v for k, v in name.items()):
                        return r.get("name") or True
                return False
            return any(r.get("name") == name for r in fr._delivery)
        return False
    db.exists = _exists
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

    class _GenericDoc(dict):
        def __getattr__(self, kk):
            try:
                return self[kk]
            except KeyError:
                raise AttributeError(kk)
        def __setattr__(self, kk, vv):
            self[kk] = vv
        def set(self, kk, vv):
            self[kk] = vv

    class _DeliveryDoc(_GenericDoc):
        def insert(self, ignore_permissions=False):
            idem = self.get("idempotency_key")
            for r in fr._delivery:
                if r.get("idempotency_key") == idem:
                    raise Exception("duplicate idempotency_key")   # mimics UNIQUE constraint
            fr._seq[0] += 1
            self["name"] = "DLV-%05d" % fr._seq[0]
            fr._delivery.append(self)            # store the live object so save() mutates it
            return self
        def save(self, ignore_permissions=False):
            return self

    class _PrefDoc(_GenericDoc):
        def insert(self, ignore_permissions=False):
            self["name"] = self.get("user")
            fr._prefs[self["user"]] = self
            return self
        def save(self, ignore_permissions=False):
            self["name"] = self.get("user")
            fr._prefs[self["user"]] = self
            return self

    def get_doc(arg, name=None):
        if isinstance(arg, dict):
            dt = arg.get("doctype")
            if dt == "EC Notification Delivery Log":
                return _DeliveryDoc(arg)
            if dt == "EC Notification Preference":
                return _PrefDoc(arg)
            return _NLDoc(arg)
        if arg == "Web Page":
            return _WPDoc(name, fr._webpages[name])
        if arg == "EC Notification Delivery Log":
            for r in fr._delivery:
                if r.get("name") == name:
                    return r
            raise Exception("delivery not found: %r" % name)
        if arg == "EC Notification Preference":
            return fr._prefs[name]
        raise Exception("unexpected get_doc(%r,%r)" % (arg, name))

    fr.get_doc = get_doc
    fr.publish_realtime = lambda **kw: fr._realtime.append(kw)
    fr.enqueue = lambda method, **kw: fr._enqueued.append(dict({"method": method}, **kw))
    fr.get_conf = lambda: fr._conf
    import json as _json
    fr.parse_json = lambda x: (_json.loads(x) if isinstance(x, str) else x)
    fr.get_roles = lambda *a, **k: list(fr._roles)
    fr.sendmail = lambda **k: fr._mail.append(k)

    import datetime as _dt
    def _now():
        return _dt.datetime(2026, 6, 22, 9, 0, 0)
    def _add(d, minutes=0, **kw):
        return (d or _now()) + _dt.timedelta(minutes=minutes)
    def _getdate(x=None):
        if x is None:
            return _now().date()
        if isinstance(x, _dt.datetime):
            return x.date()
        if isinstance(x, _dt.date):
            return x
        return _dt.date.fromisoformat(str(x)[:10])
    def _get_dt(x=None):
        if x is None:
            return _now()
        if isinstance(x, _dt.datetime):
            return x
        if isinstance(x, _dt.date):
            return _dt.datetime(x.year, x.month, x.day)
        return _dt.datetime.fromisoformat(str(x).replace("T", " ")[:19])
    def _add2(d, hours=0, minutes=0, days=0, **kw):
        return _get_dt(d) + _dt.timedelta(hours=hours, minutes=minutes, days=days)
    fr.utils = types.SimpleNamespace(
        format_datetime=lambda *a, **k: "Thu 25/06/2026 17:00",
        now_datetime=_now,
        add_to_date=_add2,
        get_datetime=_get_dt,
        getdate=_getdate,
        nowdate=lambda: str(_now().date()),
        today=lambda: str(_now().date()),
        add_days=lambda d, n: _getdate(d) + _dt.timedelta(days=int(n)),
        get_url=lambda *a, **k: "https://test.ecentric.vn",
        cint=lambda x=0: int(x) if str(x).lstrip("-").isdigit() else 0)
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
    FR._delivery[:] = []
    FR._prefs.clear()
    FR._enqueued[:] = []
    FR._conf.clear()
    FR._tasks.clear()
    FR._wtus.clear()
    FR._roles[:] = []
    FR._mail[:] = []
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
        # subject/message/source render as SAFE PLAIN TEXT via textContent (never
        # innerHTML with notification data): strips stray tags and defends XSS.
        self.assertIn("function toPlainText(", self.js)
        self.assertIn("subj.textContent = toPlainText(it.subject)", self.js)
        self.assertIn("src.textContent = toPlainText(it.source_label)", self.js)
        self.assertIn("var msgText = toPlainText(it.message)", self.js)
        self.assertNotIn("listEl.innerHTML =", self.js)

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
        # link target is the server action_url, validated same-origin; never subject/message.
        self.assertIn("function safeActionUrl(", self.js)
        self.assertIn("safeActionUrl(it.action_url)", self.js)
        self.assertNotIn("esc(it.message", self.js)
        self.assertNotIn("esc(it.subject", self.js)

    def test_single_install_guard(self):
        # re-running the asset must not stack pollers/handlers.
        self.assertIn("if (window._ecNotifCenterInstalled) { return; }", self.js)


class TestSingleBell(unittest.TestCase):
    """Single-bell hotfix: the asset must REUSE the native header bell and never render
    a second/custom bell."""

    def setUp(self):
        self.js = _read("public", "js", "notification_center.js")

    def test_reuses_native_bell_selector(self):
        # binds to the CANONICAL marker contract (no per-shell selector heuristics)
        self.assertIn('[data-ec-notification-bell="1"]', self.js)
        self.assertIn("function findBell", self.js)
        self.assertIn("document.querySelector(BELL_SELECTOR)", self.js)
        self.assertNotIn(".topbar-actions a.icon-btn", self.js)

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
        # robust dismissal: composedPath()/contains inside-check, pointerdown to close,
        # Escape to close; scroll/resize RE-ANCHOR (never close).
        self.assertIn("'Escape'", self.js)
        self.assertIn("function eventIsInside(", self.js)
        self.assertIn("ev.composedPath", self.js)
        self.assertIn("addEventListener('pointerdown'", self.js)
        self.assertIn("setAttribute('tabindex', '0')", self.js)
        # the scroll-close bug must be gone (scroll now only re-anchors):
        self.assertNotIn("window.addEventListener('scroll', function () { if (S.open) close(); }", self.js)
        self.assertIn("window.addEventListener('scroll', function () { if (S.open) position(); }", self.js)
        # no blur/focusout dismissal:
        self.assertNotIn("addEventListener('focusout'", self.js)
        self.assertNotIn("addEventListener('blur'", self.js)

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
        # Loaded as a CONTENT-HASHED bundle so deploys bust the immutable /assets cache
        # uniformly (raw un-versioned /assets path caused stale-asset on some routes).
        self.assertIn('web_include_js = ["notification_center.bundle.js"]', self.hooks,
                      "asset must load via the content-hashed bundle (cache-bust)")
        self.assertNotIn('web_include_js = ["/assets/ecentric_workspace/js/notification_center.js"]',
                         self.hooks, "must NOT use the raw un-versioned /assets path (immutable cache -> stale)")
        bundle = os.path.join(_pkg_root(), "public", "js", "notification_center.bundle.js")
        self.assertTrue(os.path.exists(bundle), "bundle entry file must exist")
        with open(bundle, encoding="utf-8") as fh:
            self.assertIn('import "./notification_center.js"', fh.read())

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
    def test_legacy_handler_neutralized_by_capture(self):
        # Click interception is ONE document-level CAPTURE-phase delegated handler,
        # resilient to header rerender; a plain left-click is fully neutralised via
        # stopImmediatePropagation so no legacy bell handler (any form) can fire.
        self.assertIn("document.addEventListener('click', onNotificationBellClick, true)", self.js)
        self.assertIn("function onNotificationBellClick(", self.js)
        self.assertIn(".closest(", self.js)
        self.assertIn("ev.stopPropagation();", self.js)
        self.assertIn("ev.stopImmediatePropagation()", self.js)

    def test_capture_handler_matches_only_ecentric_shell_bell(self):
        # ONLY elements carrying the canonical marker are bell targets
        self.assertIn("node.closest(BELL_SELECTOR)", self.js)
        self.assertIn('[data-ec-notification-bell="1"]', self.js)

    def test_marker_only_contract_no_heuristics(self):
        # ONE source of truth across all shells: the canonical marker attribute.
        self.assertIn("function getNotificationBellTarget(", self.js)
        self.assertIn('var BELL_SELECTOR = \'[data-ec-notification-bell="1"]\'', self.js)
        # no per-shell heuristics remain
        self.assertNotIn("isNotificationBell", self.js)
        self.assertNotIn("notification|notif", self.js)
        self.assertNotIn("getAttribute('title')", self.js)

    def test_non_marked_elements_are_never_bells(self):
        # settings/help/page-content carry NO marker, so the marker contract excludes
        # them inherently -- there is nothing route/title/icon-based to special-case.
        self.assertIn("node.closest(BELL_SELECTOR)", self.js)
        self.assertNotIn("inHeader(", self.js)
        self.assertNotIn(".topbar-actions, .header-actions", self.js)

    def test_button_bell_has_no_href_requirement(self):
        # a header button bell (no href) is matched; only ANCHORS keep native on modifier
        self.assertIn("target.tagName === 'A'", self.js)
        self.assertIn("if (isAnchor && !plain) { return; }", self.js)

    def test_observer_is_mount_only_with_cleanup(self):
        # MutationObserver only (re)mounts the badge on header rerender; it has a
        # single-instance guard and is disconnected on pagehide (no leak).
        self.assertIn("window.MutationObserver", self.js)
        self.assertIn("mo.observe(document.body", self.js)
        self.assertIn("mo.disconnect()", self.js)
        self.assertIn("pagehide", self.js)

    def test_plain_text_helper_uses_domparser(self):
        self.assertIn("function toPlainText(", self.js)
        self.assertIn("window.DOMParser", self.js)
        self.assertIn(".textContent", self.js)
        self.assertIn("replace(/\\s+/g, ' ').trim()", self.js)

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
        for harness_name in ("bell_click_check.js", "bell_contract_transform_check.js", "dropdown_dismissal_check.js", "delivery_runtime_check.js"):
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


# =========================================================================== #
# Notification Delivery v1 — central service, routing, idempotency, prefs, Teams
# =========================================================================== #
from ecentric_workspace.notification_center import events as ev          # noqa: E402
from ecentric_workspace.notification_center.providers import teams as tm  # noqa: E402


class TestRoutingMatrix(unittest.TestCase):
    def setUp(self):
        _reset("u@x.com"); FR.session.user = "u@x.com"

    def _r(self, et, sev=None, user="u@x.com"):
        pref = ev.get_preference(user)
        return ev.resolve_channels(et, sev or ev._DEFAULT_SEVERITY[et], pref)

    def test_inbox_and_toast_always_on(self):
        for et in ev.EVENT_TYPES:
            r = self._r(et)
            self.assertEqual(r["erp"], "deliver", et)
            self.assertEqual(r["toast"], "deliver", et)

    def test_defaults_no_saved_pref(self):
        r = self._r("task_assigned")
        self.assertEqual(r["sound"], "deliver")     # matrix True default
        self.assertEqual(r["desktop"], "skip")      # 'pref' -> off until opt-in
        self.assertEqual(r["teams"], "deliver")     # matrix True default (policy on)

    def test_pref_cells_off_by_default(self):
        r = self._r("task_due_soon")
        self.assertEqual(r["sound"], "skip")        # 'pref'
        self.assertEqual(r["teams"], "skip")        # 'pref'

    def test_saved_pref_reduces_true_channel(self):
        api.set_preferences(sound_enabled=0)        # user turns sound OFF
        r = self._r("task_assigned")
        self.assertEqual(r["sound"], "skip")        # reduced even though matrix True

    def test_saved_pref_raises_pref_channel(self):
        api.set_preferences(teams_enabled=1)        # user opts INTO teams
        r = self._r("task_due_soon")
        self.assertEqual(r["teams"], "deliver")

    def test_system_critical_desktop_always(self):
        r = self._r("system_critical")
        self.assertEqual(r["desktop"], "deliver")   # matrix True for system_critical


class TestQuietHours(unittest.TestCase):
    def _pref(self, start, end):
        return {"quiet_hours_enabled": 1, "quiet_hours_start": start,
                "quiet_hours_end": end, "minimum_severity": "info", "_exists": True,
                "sound_enabled": 1, "desktop_enabled": 1, "teams_enabled": 1}

    def test_same_day_window(self):
        p = self._pref("08:00", "10:00")
        self.assertTrue(ev.in_quiet_hours(p, now_min=9 * 60))
        self.assertFalse(ev.in_quiet_hours(p, now_min=11 * 60))

    def test_crosses_midnight(self):
        p = self._pref("22:00", "06:00")
        self.assertTrue(ev.in_quiet_hours(p, now_min=23 * 60))
        self.assertTrue(ev.in_quiet_hours(p, now_min=5 * 60))
        self.assertFalse(ev.in_quiet_hours(p, now_min=12 * 60))

    def test_disabled_or_equal_is_never_quiet(self):
        self.assertFalse(ev.in_quiet_hours({"quiet_hours_enabled": 0}))
        p = self._pref("08:00", "08:00")
        self.assertFalse(ev.in_quiet_hours(p, now_min=8 * 60))

    def test_quiet_suppresses_noisy_channels_not_toast(self):
        p = self._pref("08:00", "10:00")  # now=09:00 in stub
        r = ev.resolve_channels("task_assigned", "action_required", p)
        self.assertEqual(r["sound"], "suppress")
        self.assertEqual(r["teams"], "suppress")
        self.assertEqual(r["toast"], "deliver")     # baseline survives quiet hours
        self.assertEqual(r["erp"], "deliver")

    def test_urgent_bypasses_quiet(self):
        p = self._pref("08:00", "10:00")
        r = ev.resolve_channels("task_overdue", "urgent", p)
        self.assertEqual(r["sound"], "deliver")     # urgent ignores quiet hours


class TestSeverityAndEventGates(unittest.TestCase):
    def test_minimum_severity_suppresses_below(self):
        p = {"_exists": True, "sound_enabled": 1, "teams_enabled": 1, "desktop_enabled": 1,
             "minimum_severity": "urgent"}
        r = ev.resolve_channels("task_assigned", "action_required", p)
        self.assertEqual(r["sound"], "suppress")
        self.assertEqual(r["toast"], "deliver")     # baseline unaffected by min severity

    def test_urgent_bypasses_minimum_severity(self):
        p = {"_exists": True, "sound_enabled": 1, "minimum_severity": "urgent"}
        r = ev.resolve_channels("system_critical", "urgent", p)
        self.assertEqual(r["sound"], "deliver")

    def test_enabled_event_types_filter(self):
        p = {"_exists": True, "sound_enabled": 1, "teams_enabled": 1,
             "enabled_event_types": "approval_required"}
        r = ev.resolve_channels("task_assigned", "action_required", p)
        self.assertEqual(r["sound"], "suppress")    # event type not in user's list
        r2 = ev.resolve_channels("approval_required", "action_required", p)
        self.assertEqual(r2["sound"], "deliver")


class TestPublishEvent(unittest.TestCase):
    def setUp(self):
        _reset("admin@x.com"); FR.session.user = "admin@x.com"

    def test_publish_creates_inbox_realtime_delivery(self):
        res = ev.publish_notification_event(
            "task_assigned", "u@x.com", "Việc mới", "Bạn có việc mới",
            action_url="/app/task/T1", reference_doctype="Task", reference_name="T1")
        self.assertTrue(res["ok"]); self.assertNotIn("duplicate", res)
        self.assertEqual(len(FR._nl), 1)                      # inbox source of truth
        self.assertEqual(FR._nl[0]["for_user"], "u@x.com")
        # realtime: full contract, recipient-scoped, after commit
        self.assertEqual(len(FR._realtime), 1)
        ping = FR._realtime[0]
        self.assertEqual(ping["user"], "u@x.com")
        self.assertTrue(ping["after_commit"])
        for k in ("event_id", "event_type", "severity", "title", "message",
                  "action_url", "created_at", "unread_count", "item", "unread"):
            self.assertIn(k, ping["message"], k)
        # delivery audit rows
        byc = {d["channel"]: d["status"] for d in FR._delivery}
        self.assertEqual(byc["erp"], "Sent")
        self.assertEqual(byc["toast"], "Sent")
        self.assertEqual(byc["sound"], "Sent")
        self.assertEqual(byc["desktop"], "Skipped")          # pref off by default
        self.assertEqual(byc["teams"], "Pending")            # enqueued
        # teams enqueued on background queue (never inline)
        self.assertTrue(any(e["method"].endswith("teams.deliver") for e in FR._enqueued))
        self.assertTrue(all(e.get("enqueue_after_commit") for e in FR._enqueued))

    def test_dedupe_key_makes_second_publish_noop(self):
        for _ in range(2):
            r = ev.publish_notification_event(
                "approval_required", "u@x.com", "Cần duyệt", "",
                reference_doctype="MSO", reference_name="MSO-1")
        self.assertTrue(r.get("duplicate"))
        self.assertEqual(len(FR._nl), 1)                     # no duplicate inbox
        self.assertEqual(len(FR._realtime), 1)               # no duplicate realtime
        erp_rows = [d for d in FR._delivery if d["channel"] == "erp"]
        self.assertEqual(len(erp_rows), 1)                   # no duplicate delivery

    def test_delivery_idempotency_key_is_unique(self):
        eid = ev._event_id("k1")
        a = ev._delivery(eid, "u@x.com", "teams", "Pending")
        b = ev._delivery(eid, "u@x.com", "teams", "Pending")
        self.assertIsNotNone(a)
        self.assertIsNone(b)                                 # UNIQUE guard -> no dup row

    def test_guest_recipient_is_dropped(self):
        r = ev.publish_notification_event("mention", "Guest", "x")
        self.assertFalse(r["ok"]); self.assertEqual(len(FR._nl), 0)


class TestPreferencesAPI(unittest.TestCase):
    def setUp(self):
        _reset("a@x.com"); FR.session.user = "a@x.com"

    def test_get_defaults_when_none(self):
        out = api.get_preferences()
        self.assertTrue(out["success"])
        self.assertEqual(out["preferences"]["sound_enabled"], 1)
        self.assertEqual(out["preferences"]["desktop_enabled"], 0)

    def test_set_is_scoped_to_session_user(self):
        api.set_preferences(sound_enabled=0, teams_enabled=1, minimum_severity="urgent")
        self.assertEqual(set(FR._prefs.keys()), {"a@x.com"})   # only the session user
        out = api.get_preferences()
        self.assertEqual(out["preferences"]["sound_enabled"], 0)
        self.assertEqual(out["preferences"]["teams_enabled"], 1)
        self.assertEqual(out["preferences"]["minimum_severity"], "urgent")

    def test_set_cannot_target_another_user(self):
        # the signature has NO user param: a crafted kwarg is simply ignored.
        try:
            api.set_preferences(sound_enabled=0, user="victim@x.com")
        except TypeError:
            pass  # rejected outright is also acceptable
        self.assertNotIn("victim@x.com", FR._prefs)

    def test_guest_unauthorized(self):
        FR.session.user = "Guest"
        self.assertFalse(api.get_preferences()["success"])
        self.assertFalse(api.set_preferences(sound_enabled=1)["success"])


class TestTeamsAdapter(unittest.TestCase):
    def setUp(self):
        _reset("admin@x.com"); FR.session.user = "admin@x.com"

    def test_build_card_open_in_erp_and_plain_text(self):
        card = tm.build_card({"title": "<b>Việc</b>", "message": "<i>nội dung</i>",
                              "event_type": "task_assigned", "severity": "urgent",
                              "action_url": "/app/task/T1", "actor": "boss"})
        self.assertEqual(card["sections"][0]["activityTitle"], "Việc")     # HTML stripped
        self.assertEqual(card["sections"][0]["text"], "nội dung")
        act = card["potentialAction"][0]
        self.assertEqual(act["name"], "Open in ERP")
        self.assertEqual(act["targets"][0]["uri"], "/app/task/T1")

    def test_build_card_names_intended_recipient(self):
        card = tm.build_card({"title": "X", "event_type": "task_assigned",
                              "severity": "info", "recipient": "u@x.com"})
        facts = card["sections"][0]["facts"]
        self.assertTrue(any(f["name"] == "For" and f["value"] == "u@x.com" for f in facts))

    def test_dryrun_when_no_credential(self):
        FR._conf.clear()                                   # provider defaults to 'disabled'
        nm = ev._delivery(ev._event_id("e1"), "u@x.com", "teams", "Pending",
                          title="T", message="M", event_type="task_assigned", severity="info")
        tm.deliver(nm)
        doc = FR.get_doc("EC Notification Delivery Log", nm)
        self.assertEqual(doc["status"], "Skipped")
        self.assertEqual(doc["error_code"], "NO_CREDENTIAL")
        self.assertEqual(doc["provider"], "dryrun")

    def test_webhook_secret_never_logged_on_failure(self):
        FR._conf.update({"ec_teams_provider": "webhook",
                         "ec_teams_webhook_url": "https://secret.example/hook/AAA-SECRET"})
        orig = tm._post_webhook
        tm._post_webhook = lambda url, card: (False, "500", "teams webhook non-2xx")
        try:
            nm = ev._delivery(ev._event_id("e2"), "u@x.com", "teams", "Pending",
                              title="T", message="M", event_type="task_overdue", severity="urgent")
            tm.deliver(nm)
        finally:
            tm._post_webhook = orig
        doc = FR.get_doc("EC Notification Delivery Log", nm)
        self.assertEqual(doc["status"], "Failed")
        self.assertEqual(doc["attempt_count"], 1)
        self.assertIsNotNone(doc["next_retry_at"])         # retry scheduled
        # the secret URL must NOT appear anywhere in the recorded error
        blob = (str(doc.get("error_code")) + str(doc.get("error_message")))
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("secret.example", blob)

    def test_webhook_success_marks_sent(self):
        FR._conf.update({"ec_teams_provider": "webhook",
                         "ec_teams_webhook_url": "https://x/hook"})
        orig = tm._post_webhook
        tm._post_webhook = lambda url, card: (True, "200", "")
        try:
            nm = ev._delivery(ev._event_id("e3"), "u@x.com", "teams", "Pending",
                              title="T", message="M", event_type="task_assigned", severity="info")
            tm.deliver(nm)
        finally:
            tm._post_webhook = orig
        doc = FR.get_doc("EC Notification Delivery Log", nm)
        self.assertEqual(doc["status"], "Sent")
        self.assertIsNotNone(doc["sent_at"])

    def test_retry_sweep_requeues_due_failed(self):
        nm = ev._delivery(ev._event_id("e4"), "u@x.com", "teams", "Failed",
                          title="T", message="M", event_type="task_assigned", severity="info")
        d = FR.get_doc("EC Notification Delivery Log", nm)
        d["attempt_count"] = 1
        d["next_retry_at"] = FR.utils.now_datetime()       # due now
        FR._enqueued[:] = []
        out = tm.process_teams_retries()
        self.assertEqual(out["requeued"], 1)
        self.assertTrue(any(e["method"].endswith("teams.deliver") for e in FR._enqueued))


class TestEmitStillRoutesDelivery(unittest.TestCase):
    def setUp(self):
        _reset("a@x.com"); FR.session.user = "a@x.com"

    def test_emit_creates_inbox_and_delivery_rows(self):
        name = svc.emit("u@x.com", "Hi", "msg", document_type="Task", document_name="T9")
        self.assertIsNotNone(name)
        self.assertEqual(len(FR._nl), 1)                   # legacy contract intact
        # legacy realtime payload stays exactly {item, unread}
        self.assertEqual(set(FR._realtime[0]["message"].keys()), {"item", "unread"})
        # but multi-channel delivery rows are now also recorded (best-effort)
        chans = {d["channel"] for d in FR._delivery}
        self.assertIn("erp", chans)
        self.assertIn("toast", chans)


class TestDeliveryAssetStatics(unittest.TestCase):
    """Static guarantees about the delivery-v1 additions to the global asset:
    plain-text rendering, opt-in desktop, per-event dedupe, correct API methods, and
    NO direct Teams/secret access from the browser."""

    def setUp(self):
        self.js = _read("public", "js", "notification_center.js")

    def test_toast_uses_plaintext(self):
        self.assertIn("function pickTitle(", self.js)
        self.assertIn("toPlainText(d.title", self.js)
        self.assertNotIn("toast.innerHTML = pickTitle", self.js)

    def test_per_event_dedupe_and_persisted(self):
        self.assertIn("function markSeen(", self.js)
        self.assertIn("if (!markSeen(id)) return;", self.js)
        self.assertIn("SEEN_KEY = 'ec_notif_seen'", self.js)

    def test_desktop_is_opt_in_and_background_only(self):
        self.assertIn("function requestDesktopPermission(", self.js)
        self.assertIn("if (!document.hidden && sev !== 'urgent') return;", self.js)
        # no auto prompt on load: requestPermission only inside the opt-in handlers
        self.assertNotIn("Notification.requestPermission()", self.js.replace(" ", ""))

    def test_preferences_api_methods(self):
        self.assertIn("call('get_preferences', 'GET'", self.js)
        self.assertIn("call('set_preferences', 'POST'", self.js)

    def test_no_direct_teams_or_secret_in_browser(self):
        low = self.js.lower()
        self.assertNotIn("webhook", low)
        self.assertNotIn("ec_teams", low)
        self.assertNotIn("office.com/webhook", low)

    def test_sound_quiet_hours_and_unlock(self):
        self.assertIn("function inQuiet(", self.js)
        self.assertIn("function shouldSound(", self.js)
        self.assertIn("!S.interacted", self.js)


# =========================================================================== #
# Notification Delivery v1 — REAL business-event producer integration tests
# =========================================================================== #
import json as _json2


class _Doc:
    """Minimal Frappe-doc-like object for approval producer tests."""
    def __init__(self, **k):
        self.__dict__.update(k)
    def get(self, k, d=None):
        return getattr(self, k, d)


class TestPMProducers(unittest.TestCase):
    def setUp(self):
        _reset("boss@x.com"); FR.session.user = "boss@x.com"
        from ecentric_workspace.pm.api import notifications as pmn
        self.pmn = pmn

    def _task(self, name, state="Open", assignees=None, owner="boss@x.com", due=None):
        FR._tasks[name] = {"name": name, "subject": "T " + name, "workflow_state": state,
                           "owner": owner, "_assign": _json2.dumps(assignees or []),
                           "exp_end_date": due}

    def _by_channel(self, recipient):
        return {d["channel"]: d["status"] for d in FR._delivery if d["recipient"] == recipient}

    def test_assign_creates_exactly_one_notification_log(self):
        self._task("TASK-1", assignees=["u@x.com"])
        self.pmn.notify_users(["u@x.com"], "Ban duoc giao", "TASK-1")
        self.assertEqual(len(FR._nl), 1)
        self.assertEqual(FR._nl[0]["for_user"], "u@x.com")
        self.assertEqual(FR._nl[0]["document_type"], "Task")
        # exactly one delivery row per (recipient, channel)
        from collections import Counter
        c = Counter((d["recipient"], d["channel"]) for d in FR._delivery)
        self.assertTrue(all(v == 1 for v in c.values()), dict(c))
        byc = self._by_channel("u@x.com")
        self.assertEqual(byc["erp"], "Sent")
        self.assertEqual(byc["teams"], "Pending")        # task_assigned routes teams
        self.assertTrue(FR._nl[0]["document_name"] == "TASK-1")

    def test_self_assign_not_notified(self):
        self._task("TASK-2")
        self.pmn.notify_users(["boss@x.com"], "x", "TASK-2", from_user="boss@x.com")
        self.assertEqual(len(FR._nl), 0)

    def test_reassign_notifies_only_new_assignee(self):
        # call site computes the NEW assignee; the producer notifies that one only
        self._task("TASK-3", assignees=["old@x.com", "new@x.com"])
        self.pmn.notify_users(["new@x.com"], "x", "TASK-3")
        self.assertEqual([n["for_user"] for n in FR._nl], ["new@x.com"])

    def test_done_and_cancelled_not_notified(self):
        self._task("TASK-D", state="Done", assignees=["u@x.com"])
        self.pmn.notify_users(["u@x.com"], "x", "TASK-D")
        self._task("TASK-C", state="Cancelled", assignees=["u@x.com"])
        self.pmn.notify_users(["u@x.com"], "x", "TASK-C")
        self.assertEqual(len(FR._nl), 0)

    def test_overdue_scan_twice_no_duplicate(self):
        self._task("TASK-OV", state="Open", assignees=["u@x.com"], due="2026-06-20")
        self.pmn.pm_overdue_scan()
        self.pmn.pm_overdue_scan()                         # scheduler re-run
        self.assertEqual(len(FR._nl), 1)                   # one NL despite two runs
        self.assertEqual(len([d for d in FR._delivery if d["channel"] == "erp"]), 1)
        self.assertEqual(self._by_channel("u@x.com")["erp"], "Sent")

    def test_due_soon_scan_twice_no_duplicate(self):
        self._task("TASK-DS", state="Open", assignees=["u@x.com"], due="2026-06-23")
        self.pmn.pm_due_soon_scan()
        self.pmn.pm_due_soon_scan()                        # scheduler re-run
        self.assertEqual(len(FR._nl), 1)

    def test_teams_no_credential_skips_without_failing(self):
        self._task("TASK-T", assignees=["u@x.com"])
        self.pmn.notify_users(["u@x.com"], "x", "TASK-T")
        teams = [d for d in FR._delivery if d["channel"] == "teams"][0]
        nl_before = len(FR._nl)
        FR._conf.clear()
        tm.deliver(teams["name"])                          # background job, no credential
        self.assertEqual(teams["status"], "Skipped")
        self.assertEqual(teams["error_code"], "NO_CREDENTIAL")
        self.assertEqual(len(FR._nl), nl_before)           # business txn untouched


class TestApprovalProducer(unittest.TestCase):
    def setUp(self):
        _reset("submitter@x.com"); FR.session.user = "submitter@x.com"
        from ecentric_workspace import api as ecapi
        self.ecapi = ecapi

    def _doc(self, level=1):
        return _Doc(doctype="MSO Request", name="MSO-1", current_level=level,
                    submitted_by="submitter@x.com", owner="submitter@x.com")

    def test_approval_required_emitted_to_approver(self):
        self.ecapi._notify_approver("approver@x.com", self._doc())
        self.assertEqual(len(FR._nl), 1)
        self.assertEqual(FR._nl[0]["for_user"], "approver@x.com")
        self.assertEqual(FR._nl[0]["document_type"], "MSO Request")
        self.assertEqual(len(FR._mail), 1)                 # email still sent
        byc = {d["channel"]: d["status"] for d in FR._delivery}
        self.assertEqual(byc["erp"], "Sent")
        self.assertEqual(byc["teams"], "Pending")          # approval_required routes teams

    def test_reload_does_not_renotify(self):
        self.ecapi._notify_approver("approver@x.com", self._doc())
        self.ecapi._notify_approver("approver@x.com", self._doc())   # same stage again
        self.assertEqual(len(FR._nl), 1)                   # stable dedupe -> no re-notify

    def test_level_advance_notifies_new_approver(self):
        self.ecapi._notify_approver("approver1@x.com", self._doc(level=1))
        self.ecapi._notify_approver("approver2@x.com", self._doc(level=2))
        self.assertEqual({n["for_user"] for n in FR._nl}, {"approver1@x.com", "approver2@x.com"})

    def test_no_recipient_is_noop(self):
        self.ecapi._notify_approver(None, self._doc())
        self.assertEqual(len(FR._nl), 0)


class TestWeeklyProducer(unittest.TestCase):
    def setUp(self):
        _reset("Administrator"); FR.session.user = "Administrator"
        import sys as _sys
        import types as _t
        if "ecentric_workspace.weekly_report.service" not in _sys.modules:
            _sys.modules["ecentric_workspace.weekly_report.service"] = _t.ModuleType(
                "ecentric_workspace.weekly_report.service")
        if "ecentric_workspace.weekly_report.week_calendar" not in _sys.modules:
            wc = _t.ModuleType("ecentric_workspace.weekly_report.week_calendar")
            wc.MissingReportingWindowError = type("MissingReportingWindowError", (Exception,), {})
            _sys.modules["ecentric_workspace.weekly_report.week_calendar"] = wc
        from ecentric_workspace.weekly_report import scheduler as wsch
        self.wsch = wsch

    def _wtu(self, name, status, due, user="u@x.com", label="2026-W26"):
        FR._wtus[name] = {"name": name, "status": status, "submitter": user,
                          "week_label": label, "due_at": due}

    def test_overdue_obligation_twice_no_duplicate(self):
        self._wtu("WTU-1", "Draft", "2026-06-20 09:00:00")   # before now (2026-06-22 09:00)
        self.wsch.wr_due_overdue_scan()
        self.wsch.wr_due_overdue_scan()                       # re-run
        self.assertEqual(len(FR._nl), 1)
        self.assertEqual(FR._nl[0]["document_type"], "Weekly Team Update")

    def test_due_soon_obligation(self):
        self._wtu("WTU-2", "Draft", "2026-06-22 20:00:00")   # within 24h of now
        self.wsch.wr_due_overdue_scan()
        self.assertEqual(len(FR._nl), 1)

    def test_terminal_obligation_not_notified(self):
        self._wtu("WTU-3", "Submitted", "2026-06-20 09:00:00")
        self.wsch.wr_due_overdue_scan()
        self.assertEqual(len(FR._nl), 0)


class TestSingleNotificationLogOwner(unittest.TestCase):
    """One business event -> exactly one native Notification Log + <=1 delivery log per
    (recipient, channel); scheduler re-run never increases the counts."""

    def setUp(self):
        _reset("boss@x.com"); FR.session.user = "boss@x.com"
        from ecentric_workspace.pm.api import notifications as pmn
        self.pmn = pmn

    def test_one_event_one_log_one_delivery_each_channel(self):
        FR._tasks["TK"] = {"name": "TK", "subject": "T", "workflow_state": "Open",
                           "owner": "boss@x.com", "_assign": _json2.dumps(["u@x.com"]),
                           "exp_end_date": "2026-06-20"}
        self.pmn.pm_overdue_scan()
        self.pmn.pm_overdue_scan()
        self.assertEqual(len(FR._nl), 1)
        from collections import Counter
        c = Counter((d["recipient"], d["channel"]) for d in FR._delivery)
        self.assertTrue(all(v == 1 for v in c.values()), dict(c))
