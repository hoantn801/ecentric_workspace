# Copyright (c) 2026, eCentric and contributors
"""Phieu trong chat - chay KHONG can bench.

    python -m unittest ecentric_workspace.chat.tests.test_phieu

Kiem: doc link phieu trong tin nhan (phieu.py thuan); gateway tren frappe GIA + registry GIA
(the mo /approvals, gan the khi dan link + kiem quyen nguoi gui, bot chi gui cho nguoi co chat,
moi loi bi nuot); dang ky hook chi noi them; patch chon dong xem truoc.
"""
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.chat import constants as C  # noqa: E402
from ecentric_workspace.chat import phieu as P  # noqa: E402

HOSTS = {"team.ecentric.vn"}
ROUTES = {"/approvals/payment-request", "/approvals/contract-review"}
PAYR = "EC-PAYR-2026-00042"


class TestFindLink(unittest.TestCase):

    def test_plain_and_html(self):
        t = "xem giúp https://team.ecentric.vn/approvals/payment-request?id=%s nhé." % PAYR
        self.assertEqual(P.find_approval_link(t, HOSTS, ROUTES), ("/approvals/payment-request", PAYR))
        h = ('<p><a href="https://team.ecentric.vn/approvals/contract-review?x=1&amp;id=CTR%2D1">'
             'link</a></p>')
        self.assertEqual(P.find_approval_link(h, HOSTS, ROUTES), ("/approvals/contract-review", "CTR-1"))

    def test_rejects(self):
        for t in ("https://evil.vn/approvals/payment-request?id=X",
                  "https://team.ecentric.vn/approvals/unknown?id=X",
                  "https://team.ecentric.vn/approvals/payment-request",
                  "https://team.ecentric.vn/approvals/payment-request?id=",
                  "team.ecentric.vn/approvals/payment-request?id=X", "", None):
            self.assertIsNone(P.find_approval_link(t, HOSTS, ROUTES), t)
        self.assertIsNone(P.find_approval_link("https://team.ecentric.vn/approvals/payment-request?id="
                                               + "A" * 141, HOSTS, ROUTES))

    def test_first_valid_wins_and_route_norm(self):
        t = ("https://evil.vn/approvals/payment-request?id=BAD "
             "https://TEAM.ecentric.vn/approvals/payment-request/?id=GOOD) "
             "https://team.ecentric.vn/approvals/contract-review?id=LATER")
        self.assertEqual(P.find_approval_link(t, HOSTS, ROUTES), ("/approvals/payment-request", "GOOD"))
        self.assertEqual(P.norm_route("approvals/x/"), "/approvals/x")
        self.assertEqual(P.norm_route(""), "")

    def test_bot_html_escapes(self):
        out = P.bot_html('Cần duyệt: <img src=x onerror=1>',
                         "<b>Người gửi:</b> Lâm &amp; Co<br><b>Số tiền:</b> 1,000 VND",
                         'https://team.ecentric.vn/approvals/payment-request?id=A"><script>')
        self.assertNotIn("<img", out)
        self.assertNotIn("<script", out)
        self.assertIn("Người gửi: Lâm &amp; Co<br>Số tiền: 1,000 VND", out)
        self.assertIn("Mở phiếu", out)
        self.assertNotIn("Mở phiếu", P.bot_html("t", "", "javascript:alert(1)"))


# --------------------------------------------------------------------------- frappe gia
class _Doc(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class _Bot(object):
    def __init__(self, f):
        self.f = f

    def send_direct_message(self, user, text=None, link_doctype=None, link_document=None):
        self.f.sent.append((user, text, link_doctype, link_document))


def _fake_frappe():
    f = types.ModuleType("frappe")
    f.conf = {}
    f.session = types.SimpleNamespace(user="lam.nguyen@ecentric.vn")
    f.local = types.SimpleNamespace(request=None)
    f.enqueued, f.sent, f.errors, f.warned = [], [], [], []
    f.docs = {("EC Payment Request", PAYR)}
    f.readers = {("EC Payment Request", PAYR): {"lam.nguyen@ecentric.vn", "hoan.tran@ecentric.vn"}}
    f.roles = {"hoan.tran@ecentric.vn": ["Raven User"], "lam.nguyen@ecentric.vn": ["Raven User"]}
    f.raven_users = {"hoan.tran@ecentric.vn", "lam.nguyen@ecentric.vn"}
    f.bots = set()
    f.delivery = {}
    f.installed = ["frappe", "raven", "ecentric_workspace"]
    store = {}
    f.cache = lambda: types.SimpleNamespace(
        get_value=lambda k: store.get(k),
        set_value=lambda k, v, expires_in_sec=None: store.__setitem__(k, v))
    f._store = store
    f.get_all = lambda dt, **kw: [{"name": "PAYMENT_REQUEST", "route": "/approvals/payment-request"},
                                  {"name": "CONTRACT_REVIEW", "route": "approvals/contract-review"},
                                  {"name": "MONTHLY_BUDGET", "route": ""},
                                  {"name": "NOT_IN_REGISTRY", "route": "/approvals/x"}]
    f.utils = types.SimpleNamespace(get_url=lambda: "https://team.ecentric.vn")
    f.get_installed_apps = lambda: list(f.installed)
    f.get_roles = lambda u=None: list(f.roles.get(u, []))
    f.has_permission = lambda dt, ptype="read", doc=None, user=None: user in f.readers.get((dt, doc), set())

    def exists(dt, name=None):
        if dt == "Raven Bot":
            return name in f.bots
        return (dt, name) in f.docs
    f.db = types.SimpleNamespace(exists=exists)

    def get_value(dt, filters, fields=None, as_dict=False):
        if dt == "Raven User":
            return "RU" if filters.get("user") in f.raven_users and filters.get("enabled") else None
        if dt == "EC Notification Delivery Log":
            row = f.delivery.get(filters)
            return _Doc(row) if row else None
        return None
    f.db.get_value = get_value

    def get_doc(arg, name=None):
        if isinstance(arg, dict):
            def insert(ignore_permissions=False):
                f.bot_inserts = getattr(f, "bot_inserts", 0) + 1
                f.bots.add(arg["bot_name"])
                return _Bot(f)
            return types.SimpleNamespace(insert=insert, send_direct_message=_Bot(f).send_direct_message)
        return _Bot(f)
    f.get_doc = get_doc

    def enqueue(path, **kw):
        f.enqueued.append((path, kw))
    f.enqueue = enqueue
    f.logger = lambda name=None: types.SimpleNamespace(warning=lambda *a, **k: f.warned.append(a[0]))
    f.log_error = lambda title=None, message=None: f.errors.append(title)
    f.get_traceback = lambda: "tb"
    return f


def _fake_registry():
    reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
    reg.APPROVAL_DEFINITIONS = {
        "PAYMENT_REQUEST": types.SimpleNamespace(business_doctype="EC Payment Request"),
        "CONTRACT_REVIEW": types.SimpleNamespace(business_doctype="EC Contract Review Request"),
        "MONTHLY_BUDGET": types.SimpleNamespace(business_doctype="EC Monthly Budget"),
    }
    reg.BUSINESS_DOCTYPE_DEFINITIONS = {d.business_doctype: d for d in reg.APPROVAL_DEFINITIONS.values()}
    return reg


_OWN = ("frappe", "ecentric_workspace.chat.phieu_gateway",
        "ecentric_workspace.approval_center.shared.registry",
        "ecentric_workspace.chat.patches.p001_the_phieu_preview")
_SAVED = {}


def setUpModule():
    for name in _OWN:
        _SAVED[name] = sys.modules.get(name)
        sys.modules.pop(name, None)
    sys.modules["frappe"] = _fake_frappe()
    sys.modules["ecentric_workspace.approval_center.shared.registry"] = _fake_registry()


def tearDownModule():
    for name, mod in _SAVED.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


class _Case(unittest.TestCase):
    def setUp(self):
        sys.modules["frappe"] = self.f = _fake_frappe()
        sys.modules.pop("ecentric_workspace.chat.phieu_gateway", None)
        import importlib
        self.G = importlib.import_module("ecentric_workspace.chat.phieu_gateway")


class TestDocumentLink(_Case):

    def test_routes(self):
        self.assertEqual(self.G.document_link("EC Payment Request", PAYR),
                         "/approvals/payment-request?id=" + PAYR)
        self.assertEqual(self.G.document_link("EC Contract Review Request", "A B/1"),
                         "/approvals/contract-review?id=A%20B%2F1")
        self.assertIsNone(self.G.document_link("EC Monthly Budget", "X"))   # route rong
        self.assertIsNone(self.G.document_link("Sales Order", "SO-1"))      # khong phai phieu
        self.f.conf[C.PHIEU_KILL_SWITCH] = 1
        self.assertIsNone(self.G.document_link("EC Payment Request", PAYR))

    def test_route_map_cached(self):
        self.G.document_link("EC Payment Request", PAYR)
        self.f.get_all = lambda *a, **k: (_ for _ in ()).throw(AssertionError("khong doc lai"))
        self.assertTrue(self.G.document_link("EC Payment Request", PAYR))


class TestPastedLink(_Case):
    URL = "https://team.ecentric.vn/approvals/payment-request?id=" + PAYR

    def _msg(self, **kw):
        d = _Doc(message_type="Text", text="<p>%s</p>" % self.URL, owner="lam.nguyen@ecentric.vn")
        d.update(kw)
        self.G.on_raven_message_before_insert(d)
        return d

    def test_attaches_card(self):
        d = self._msg()
        self.assertEqual((d.link_doctype, d.link_document, d.hide_link_preview),
                         ("EC Payment Request", PAYR, 1))

    def test_left_alone(self):
        # phieu da xoa nhung nguoi gui tung co quyen: van khong gan the
        self.f.readers[("EC Payment Request", "EC-PAYR-0")] = {"lam.nguyen@ecentric.vn"}
        cases = [dict(owner="ngoai@ecentric.vn"),              # nguoi gui khong xem duoc phieu
                 dict(text="<p>%s</p>" % self.URL.replace(PAYR, "EC-PAYR-0")),   # da xoa
                 dict(is_bot_message=1),
                 dict(link_doctype="X", link_document="Y"),
                 dict(message_type="Image"),
                 dict(text="khong co link")]
        for kw in cases:
            d = self._msg(**kw)
            self.assertEqual(d.link_document, kw.get("link_document"), kw)
            self.assertFalse(d.hide_link_preview, kw)
        self.f.conf[C.PHIEU_KILL_SWITCH] = 1
        self.assertIsNone(self._msg().link_document)

    def test_errors_swallowed(self):
        self.f.has_permission = lambda *a, **k: 1 / 0
        d = self._msg()
        self.assertIsNone(d.link_document)
        self.assertTrue(self.f.warned)


class TestBot(_Case):

    def _log(self, **kw):
        d = _Doc(name="DL1", channel="erp", status="Sent", event_type="approval_required")
        d.update(kw)
        self.G.on_delivery_log_after_insert(d)
        return d

    def test_enqueue_only_erp_sent_approval(self):
        self._log()
        self.assertEqual(self.f.enqueued[-1][0], "ecentric_workspace.chat.phieu_gateway.send_bot_message")
        self.assertTrue(self.f.enqueued[-1][1]["enqueue_after_commit"])
        n = len(self.f.enqueued)
        for kw in (dict(channel="teams"), dict(status="Skipped"), dict(event_type="task_assigned")):
            self._log(**kw)
        self.f.conf[C.BOT_KILL_SWITCH] = 1
        self._log()
        self.assertEqual(len(self.f.enqueued), n)

    def _row(self, **kw):
        row = dict(recipient="hoan.tran@ecentric.vn", title="Cần duyệt: Thanh toán vận chuyển",
                   message="<b>Người gửi:</b> Lâm", action_url="", reference_doctype="EC Payment Request",
                   reference_name=PAYR)
        row.update(kw)
        self.f.delivery["DL1"] = row

    def test_send_with_card_and_bot_created_once(self):
        self._row()
        self.G.send_bot_message("DL1")
        self.G.send_bot_message("DL1")
        self.assertEqual((self.f.bots, self.f.bot_inserts), ({C.BOT_NAME}, 1))
        user, text, dt, dn = self.f.sent[0]
        self.assertEqual((user, dt, dn), ("hoan.tran@ecentric.vn", "EC Payment Request", PAYR))
        self.assertIn("https://team.ecentric.vn/approvals/payment-request?id=" + PAYR, text)

    def test_skips(self):
        for kw in (dict(recipient="ngoai@ecentric.vn"), dict(recipient="Administrator")):
            self._row(**kw)
            self.G.send_bot_message("DL1")
        self.f.roles["hoan.tran@ecentric.vn"] = []          # mat role Raven User
        self._row()
        self.G.send_bot_message("DL1")
        self.assertEqual(self.f.sent, [])
        self.f.installed = ["frappe"]
        self.f.roles["hoan.tran@ecentric.vn"] = ["Raven User"]
        self.G.send_bot_message("DL1")
        self.assertEqual(self.f.sent, [])

    def test_no_card_for_missing_doc_and_errors_logged(self):
        self._row(reference_name="EC-PAYR-GONE", action_url="https://team.ecentric.vn/approvals/x?id=1")
        self.G.send_bot_message("DL1")
        self.assertEqual(self.f.sent[-1][2:], (None, None))
        self.f.db.get_value = lambda *a, **k: 1 / 0
        self.G.send_bot_message("DL1")
        self.assertEqual(self.f.errors, ["ec_chat bot"])


class TestHooksAndPatch(unittest.TestCase):

    def test_hooks_append_only(self):
        with io.open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            hooks = fh.read()
        tail = hooks[hooks.index("raven_document_link_override = list("):]
        ns = {"doc_events": {"Raven Message": {"before_insert": "other.hook"}},
              "raven_document_link_override": ["x.y"]}
        exec(tail, ns)
        self.assertEqual(ns["raven_document_link_override"],
                         ["x.y", "ecentric_workspace.chat.phieu_gateway.document_link"])
        self.assertEqual(ns["doc_events"]["Raven Message"]["before_insert"],
                         ["other.hook", "ecentric_workspace.chat.phieu_gateway.on_raven_message_before_insert"])
        self.assertEqual(ns["doc_events"]["EC Notification Delivery Log"]["after_insert"],
                         ["ecentric_workspace.chat.phieu_gateway.on_delivery_log_after_insert"])
        with io.open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("ecentric_workspace.chat.patches.p001_the_phieu_preview", fh.read())

    def test_patch_fields(self):
        sys.modules["frappe"] = _fake_frappe()
        import importlib
        p = importlib.import_module("ecentric_workspace.chat.patches.p001_the_phieu_preview")
        self.assertEqual(p.fields_for(["reason", "payment_amount", "department", "requested_by",
                                       "bank_account_number", "submitted_at", "amount"]),
                         ["requested_by", "department", "submitted_at", "payment_amount"])
        self.assertEqual(p.fields_for(["requested_by"]), ["requested_by"])


if __name__ == "__main__":
    unittest.main()
