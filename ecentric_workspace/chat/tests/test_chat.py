# Copyright (c) 2026, eCentric and contributors
"""Chat noi bo (lop gan Raven vao ERP) - chay KHONG can bench.

    python -m unittest ecentric_workspace.chat.tests.test_chat

Kiem:
  * inbox.py (thuan): sap xep, chua doc, bo kenh luu tru, xem truoc, mo kenh trong iframe CHI
    khi kenh nam trong danh sach Raven tra cho chinh nguoi do;
  * gateway + api tren frappe GIA va Raven GIA: trang thai (tat / chua cai / chua co quyen),
    bat loi Raven, khong lo truong thua (so dien thoai) cua Raven User;
  * shell: o Tin nhan chi xuat hien LUC RENDER khi chat bat; ban nuong trong file trang khong doi;
    markup server == markup ec_shell.js;
  * trang www/chat ve dung trang thai dau (jinja2);
  * ec_chat.js (node): ham thuan + chong XSS.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.chat import constants as C  # noqa: E402
from ecentric_workspace.chat import inbox as I  # noqa: E402

ME = "hoan.tran@ecentric.vn"
LAM = "lam.nguyen@ecentric.vn"
DONG = "dong.diep@ecentric.vn"
USERS = {ME: {"full_name": "Hoàn Trần", "user_image": ""},
         LAM: {"full_name": "Lâm Nguyễn", "user_image": "/files/lam.png"},
         DONG: {"full_name": "Đông Diệp", "user_image": ""}}


def _det(content, owner, mtype="Text", **kw):
    d = {"message_id": "m", "content": content, "message_type": mtype, "owner": owner}
    d.update(kw)
    return json.dumps(d)


def _channels():
    return [
        {"name": "ecentric-operation", "channel_name": "operation", "type": "Public", "workspace": "eCentric",
         "is_archived": 0, "last_message_timestamp": "2026-10-05 09:18:02.1",
         "last_message_details": _det("<p>Lô ACME về kho <b>sáng mai</b></p>", DONG)},
        {"name": "ecentric-brand-acme", "channel_name": "brand-acme", "type": "Private", "workspace": "eCentric",
         "is_archived": 0, "last_message_timestamp": "2026-10-05 08:55:00",
         "last_message_details": _det("", LAM, mtype="File")},
        {"name": "ecentric-cu", "channel_name": "kênh cũ", "type": "Open", "workspace": "eCentric",
         "is_archived": 1, "last_message_timestamp": "2026-10-05 10:00:00",
         "last_message_details": _det("cũ", DONG)},
        {"name": "ecentric-general", "channel_name": "general", "type": "Open", "workspace": "eCentric",
         "is_archived": 0, "last_message_timestamp": None, "last_message_details": None},
    ]


def _dms():
    return [
        {"name": "dm-lam", "is_direct_message": 1, "peer_user_id": LAM, "is_archived": 0,
         "last_message_timestamp": "2026-10-05 09:21:00",
         "last_message_details": _det("Anh ơi phiếu 00053 em gửi rồi &amp; anh duyệt giúp", LAM)},
        {"name": "dm-dong", "is_direct_message": 1, "peer_user_id": DONG, "is_archived": 0,
         "last_message_timestamp": "2026-10-04 17:00:00",
         "last_message_details": _det("Ok, mai mình check lại kho", ME)},
        {"name": "dm-never", "is_direct_message": 1, "peer_user_id": "x@ecentric.vn", "is_archived": 0,
         "last_message_timestamp": None, "last_message_details": None},
    ]


UNREAD = [{"name": "dm-lam", "unread_count": 1}, {"name": "ecentric-operation", "unread_count": 3},
          {"name": "ecentric-brand-acme", "unread_count": "2"}]


class TestInbox(unittest.TestCase):

    def box(self, **kw):
        return I.build_inbox(_channels(), _dms(), UNREAD, USERS, ME, **kw)

    def test_newest_first_archived_and_untouched_dm_dropped(self):
        ids = [i["id"] for i in self.box()["items"]]
        self.assertEqual(ids, ["dm-lam", "ecentric-operation", "ecentric-brand-acme", "dm-dong",
                               "ecentric-general"])
        self.assertNotIn("ecentric-cu", ids)
        self.assertNotIn("dm-never", ids)

    def test_total_counts_every_channel_not_only_visible_rows(self):
        self.assertEqual(self.box(limit=1)["total_unread"], 6)
        self.assertEqual(len(self.box(limit=1)["items"]), 1)

    def test_unread_only(self):
        ids = [i["id"] for i in self.box(unread_only=True)["items"]]
        self.assertEqual(ids, ["dm-lam", "ecentric-operation", "ecentric-brand-acme"])

    def test_row_shape(self):
        rows = {i["id"]: i for i in self.box()["items"]}
        dm = rows["dm-lam"]
        self.assertEqual((dm["kind"], dm["title"], dm["avatar"], dm["unread"]),
                         ("dm", "Lâm Nguyễn", "/files/lam.png", 1))
        self.assertEqual(dm["preview"], "Anh ơi phiếu 00053 em gửi rồi & anh duyệt giúp")
        self.assertEqual(dm["href"], "/chat?c=dm-lam")
        op = rows["ecentric-operation"]
        self.assertEqual(op["preview"], "Đông Diệp: Lô ACME về kho sáng mai")
        self.assertFalse(op["is_private"])
        self.assertTrue(rows["ecentric-brand-acme"]["is_private"])
        self.assertEqual(rows["ecentric-brand-acme"]["preview"], "Lâm Nguyễn: [Tệp]")
        self.assertEqual(rows["dm-dong"]["preview"], "Bạn: Ok, mai mình check lại kho")
        self.assertEqual(rows["ecentric-general"]["preview"], "")
        self.assertEqual(rows["dm-dong"]["initials"], "ĐD")

    def test_preview_truncates_and_strips(self):
        long = "<p>" + "a" * 200 + "</p>"
        out = I.preview_text(_det(long, LAM))
        self.assertEqual(len(out), C.PREVIEW_LEN)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(I.preview_text("not json"), "")
        self.assertEqual(I.preview_text(None), "")
        self.assertEqual(I.preview_text(_det("", LAM, mtype="Image")), "[Ảnh]")

    def test_bot_sender_named_by_bot(self):
        d = _det("Phiếu đã duyệt", "Administrator", is_bot_message=1, bot="Approval Bot")
        self.assertEqual(I._preview(d, ME, USERS, False), "Approval Bot: Phiếu đã duyệt")

    def test_self_dm(self):
        dms = [{"name": "dm-me", "is_direct_message": 1, "is_self_message": 1, "peer_user_id": ME,
                "last_message_timestamp": "2026-10-05 07:00:00", "last_message_details": _det("note", ME)}]
        item = I.build_inbox([], dms, [], USERS, ME)["items"][0]
        self.assertEqual(item["title"], "Hoàn Trần (bạn)")

    def test_bad_unread_rows_ignored(self):
        box = I.build_inbox([], [], [{"name": "x", "unread_count": "abc"}, {"name": "y", "unread_count": -4}],
                            {}, ME)
        self.assertEqual(box["total_unread"], 0)


class TestRavenPath(unittest.TestCase):

    def test_only_own_channels_open(self):
        ch, dm = _channels(), _dms()
        self.assertEqual(I.raven_path("dm-lam", ch, dm), "/raven/dm-channel/dm-lam")
        self.assertEqual(I.raven_path("ecentric-operation", ch, dm), "/raven/eCentric/ecentric-operation")
        # kenh khong nam trong danh sach cua nguoi nay (vd kenh rieng cua nguoi khac) -> trang dau
        self.assertEqual(I.raven_path("ecentric-bi-mat", ch, dm), "/raven/")

    def test_rejects_traversal_and_encodes(self):
        self.assertEqual(I.safe_channel_id("../app"), "")
        self.assertEqual(I.safe_channel_id("a\\b"), "")
        self.assertEqual(I.safe_channel_id("x" * 141), "")
        self.assertEqual(I.safe_channel_id(None), "")
        ch = [{"name": "kênh a&b", "workspace": "Công ty", "type": "Open"}]
        self.assertEqual(I.raven_path("kênh a&b", ch, []),
                         "/raven/C%C3%B4ng%20ty/k%C3%AAnh%20a%26b")


class TestAccessState(unittest.TestCase):

    def test_order(self):
        self.assertEqual(I.access_state(True, True, True), I.STATE_DISABLED)
        self.assertEqual(I.access_state(False, False, True), I.STATE_NOT_INSTALLED)
        self.assertEqual(I.access_state(False, True, False), I.STATE_NO_ACCESS)
        self.assertEqual(I.access_state(False, True, True), I.STATE_OK)
        self.assertEqual(I.state_message(I.STATE_OK), "")
        self.assertIn("Raven User", I.state_message(I.STATE_NO_ACCESS))


# ---------------------------------------------------------------- frappe gia --
_SAVED = {}
_OWN = ("frappe", "ecentric_workspace.chat.gateway", "ecentric_workspace.chat.api",
        "ecentric_workspace.chat.pages", "ecentric_workspace.shell.server_nav")


class _Cache(object):
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v


def _fake_frappe():
    f = types.ModuleType("frappe")
    f.conf = {}
    f.installed = ["frappe", "erpnext", "raven", "ecentric_workspace"]
    f.roles = {ME: ["System User", "Raven User"], LAM: ["System User"]}
    f.session = types.SimpleNamespace(user=ME)
    f.local = types.SimpleNamespace(request=None, response={}, flags=types.SimpleNamespace())
    f.logged = []
    f.raven = {}
    f._cache = _Cache()
    f.cache = lambda: f._cache
    f._ = lambda s: s
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f.get_installed_apps = lambda: list(f.installed)
    f.get_roles = lambda user=None: list(f.roles.get(user or f.session.user, []))
    f.get_attr = lambda path: f.raven[path]
    f.form_dict = {}

    def log_error(title=None, **kw):
        f.logged.append(title)
    f.log_error = log_error

    class Redirect(Exception):
        pass
    f.Redirect = Redirect
    return f


def setUpModule():
    for name in _OWN:
        _SAVED[name] = sys.modules.get(name)
        sys.modules.pop(name, None)
    sys.modules["frappe"] = _fake_frappe()


def tearDownModule():
    for name, mod in _SAVED.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _raven_ok(frappe):
    frappe.raven = {
        "raven.api.raven_channel.get_all_channels":
            lambda hide_archived=True: {"channels": _channels(), "dm_channels": _dms()},
        "raven.api.raven_message.get_unread_count_for_channels": lambda: list(UNREAD),
        "raven.api.raven_users.get_list": lambda: [
            dict(name=k, full_name=v["full_name"], user_image=v["user_image"], contact_number="0909")
            for k, v in USERS.items()],
    }


class _FrappeCase(unittest.TestCase):
    def setUp(self):
        import frappe
        self.f = frappe
        frappe.conf.clear()
        frappe.installed = ["frappe", "raven", "ecentric_workspace"]
        frappe.session.user = ME
        frappe.local.response = {}
        frappe.logged[:] = []
        frappe._cache.d.clear()
        _raven_ok(frappe)


class TestGatewayApi(_FrappeCase):

    def test_states(self):
        from ecentric_workspace.chat import api, gateway as G
        self.assertTrue(G.chat_enabled())
        self.assertEqual(api.get_unread_total()["data"], {"state": "ok", "total": 6})
        self.f.session.user = LAM
        d = api.get_inbox()["data"]
        self.assertEqual((d["state"], d["items"]), ("no_access", []))
        self.f.session.user = ME
        self.f.conf[C.KILL_SWITCH] = 1
        self.assertFalse(G.chat_enabled())
        self.assertEqual(api.get_inbox()["data"]["state"], "disabled")
        self.f.conf.clear()
        self.f.installed = ["frappe"]
        self.assertFalse(G.chat_enabled())
        self.assertEqual(api.get_unread_total()["data"]["state"], "not_installed")

    def test_guest_refused(self):
        from ecentric_workspace.chat import api
        self.f.session.user = "Guest"
        r = api.get_inbox()
        self.assertFalse(r["success"])
        self.assertEqual(self.f.local.response.get("http_status_code"), 403)

    def test_inbox_and_unread_filter(self):
        from ecentric_workspace.chat import api
        r = api.get_inbox()
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["total_unread"], 6)
        self.assertEqual(r["data"]["items"][0]["id"], "dm-lam")
        self.assertEqual(len(api.get_inbox(unread_only="1")["data"]["items"]), 3)

    def test_user_cards_drop_extra_fields(self):
        from ecentric_workspace.chat import gateway as G
        cards = G.user_cards()
        self.assertEqual(set(cards[LAM]), {"full_name", "user_image"})
        self.assertNotIn("0909", json.dumps(cards))

    def test_raven_failure_is_contained_and_logged_once(self):
        from ecentric_workspace.chat import api

        def boom(**kw):
            raise RuntimeError("raven renamed")
        self.f.raven["raven.api.raven_channel.get_all_channels"] = boom
        self.f.raven["raven.api.raven_message.get_unread_count_for_channels"] = boom
        for _ in range(3):
            self.assertFalse(api.get_inbox()["success"])
            self.assertEqual(api.get_unread_total()["message"], C.MSG_LOAD_FAILED)
        self.assertEqual(self.f.logged, ["ec_chat"])


class TestPage(_FrappeCase):

    def _ctx(self, **form):
        from ecentric_workspace.chat import pages
        self.f.form_dict = dict(form)
        ctx = types.SimpleNamespace()
        ctx.update = lambda d: ctx.__dict__.update(d)
        return pages.get_context(ctx)

    def test_frame_src(self):
        self.assertEqual(self._ctx().chat_src, "/raven/")
        self.assertEqual(self._ctx(c="dm-lam").chat_src, "/raven/dm-channel/dm-lam")
        self.assertEqual(self._ctx(c="ecentric-bi-mat").chat_src, "/raven/")
        c = self._ctx(c="ecentric-operation")
        self.assertEqual((c.chat_state, c.no_cache), ("ok", 1))
        self.assertIn('data-ec-shell-chat-slot="1"', c.ecc_topbar)

    def test_no_access_has_no_frame(self):
        self.f.session.user = LAM
        c = self._ctx(c="dm-lam")
        self.assertEqual((c.chat_state, c.chat_src), ("no_access", ""))

    def test_guest_redirected_to_login(self):
        self.f.session.user = "Guest"
        with self.assertRaises(self.f.Redirect):
            self._ctx()
        self.assertEqual(self.f.local.flags.redirect_location, "/login?redirect-to=/chat")

    def test_template_renders_each_state(self):
        import jinja2
        with io.open(os.path.join(APP, "www", "chat", "index.html"), encoding="utf-8") as fh:
            src = fh.read()
        base = ("{% block style %}{% endblock %}{% block navbar %}NAV{% endblock %}"
                "{% block content %}{% endblock %}{% block footer %}FOOT{% endblock %}")
        env = jinja2.Environment(loader=jinja2.DictLoader({"base.html": base, "p.html": src}),
                                 autoescape=False)
        tpl = env.get_template("p.html")
        ok = tpl.render(base_template_path="base.html", title="Chat nội bộ", chat_state="ok",
                        chat_src="/raven/dm-channel/a\"b", chat_message="", ecc_css="x.css",
                        ecc_shell_mount="<aside></aside>", ecc_topbar="TOP")
        self.assertIn('<iframe class="ecc-frame" src="/raven/dm-channel/a&#34;b"', ok)
        self.assertNotIn("NAV", ok)
        self.assertNotIn("FOOT", ok)
        no = tpl.render(base_template_path="base.html", title="t", chat_state="no_access", chat_src="",
                        chat_message=C.MSG_NO_ACCESS, ecc_css="x.css", ecc_shell_mount="", ecc_topbar="")
        self.assertNotIn("<iframe", no)
        self.assertIn("Raven User", no)


class TestShellSlot(_FrappeCase):
    """O Tin nhan: chi luc render, ban nuong khong doi, server == JS."""

    def test_baked_header_unchanged_and_chat_prepends_once(self):
        from ecentric_workspace.shell import fallback as fb
        base = fb.render_tbright_inner()
        self.assertNotIn("data-ec-shell-chat-slot", base)
        with_chat = fb.render_tbright_inner(chat=True)
        self.assertEqual(with_chat, fb.render_chat_slot() + base)
        self.assertEqual(with_chat.count('data-ec-shell-chat-slot="1"'), 1)
        self.assertIn('href="/chat"', with_chat)
        self.assertNotIn("data-ec-shell-chat", fb.render_topbar_inner("/home"))

    def test_server_render_adds_slot_only_when_enabled(self):
        from ecentric_workspace.shell import server_nav as sn
        hub = io.open(os.path.join(APP, "approval_center", "ui", "hub", "main_section.html"),
                      encoding="utf-8").read()
        self.assertEqual(hub.count(sn.TBRIGHT_OPEN), 1)
        out = sn.fill_shell_mount({"main_section": hub, "route": "approvals"})["main_section"]
        self.assertEqual(out.count('data-ec-shell-chat-slot="1"'), 1)
        again = sn.fill_shell_mount({"main_section": out, "route": "approvals"})
        self.assertEqual((again or {"main_section": out})["main_section"].count('data-ec-shell-chat-slot="1"'), 1)
        self.f.conf[C.KILL_SWITCH] = 1
        off = sn.fill_shell_mount({"main_section": hub, "route": "approvals"})
        self.assertNotIn("data-ec-shell-chat-slot", (off or {"main_section": hub})["main_section"])

    def test_two_header_regions_left_alone(self):
        from ecentric_workspace.shell import server_nav as sn
        two = (sn.TBRIGHT_OPEN + "a</div>") * 2
        self.assertIsNone(sn.rebuild_tbright(two, True))
        self.assertIsNone(sn.rebuild_tbright("", True))

    def test_js_emits_identical_slot_markup(self):
        from ecentric_workspace.shell import fallback as fb
        js = io.open(os.path.join(APP, "public", "js", "ec_shell.js"), encoding="utf-8").read()
        # ba manh chu NGUYEN VAN ghep thanh o; ec_shell.js phai chua dung tung manh (chuoi JS
        # bi cat dong tai dung cac ranh gioi nay)
        f1 = '<a class="ec-shell-iconbtn ec-shell-chat" href="/chat" data-ec-shell-chat-slot="1" '
        f2 = 'aria-label="Tin nhắn" title="Tin nhắn" aria-haspopup="dialog" aria-expanded="false">'
        f3 = '<span class="ec-shell-reminder-badge" data-ec-shell-chat-badge="1" hidden></span>'
        self.assertEqual(fb.render_chat_slot(), f1 + f2 + fb._svg("chat") + f3 + "</a>")
        for frag in (f1, f2, f3):
            self.assertIn(frag, js, frag)
        self.assertIn("' + svg('chat') +", js)
        self.assertIn("chat:'" + fb.ICONS["chat"] + "'", js)
        self.assertIn("S.boot && S.boot.chat_enabled", js)
        self.assertIn("ec-shell:header-rendered", js)
        # o chat dung TRUOC hop Viec cua toi, giong ban server
        self.assertLess(js.index("ec-shell-chat"), js.index("data-ec-shell-action-slot=\"1\" aria-label"))

    def test_nav_item(self):
        from ecentric_workspace.shell import nav
        it = [i for i in nav.HOME_PORTAL_ITEMS if i["key"] == "home.portal.chat"]
        self.assertEqual(len(it), 1)
        it = it[0]
        self.assertEqual((it["route"], it["icon"], it["badge_source"], it.get("alias")),
                         ("/chat", "chat", "chat.unread", None))
        self.assertEqual(nav.resolve_context("/chat"), "home")
        js = io.open(os.path.join(APP, "public", "js", "ec_chat.js"), encoding="utf-8").read()
        self.assertIn('[data-ec-shell-badge="chat.unread"]', js)

    def test_hooks_load_assets(self):
        hooks = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertIn('web_include_js.append("ec_chat.bundle.js")', hooks)
        self.assertIn('web_include_css.append("ec_chat.bundle.css")', hooks)
        for rel in (("public", "js", "ec_chat.bundle.js"), ("public", "css", "ec_chat.bundle.css"),
                    ("public", "css", "ec_chat_page.css")):
            self.assertTrue(os.path.isfile(os.path.join(APP, *rel)), rel)


class TestChatJs(unittest.TestCase):
    """ec_chat.js chay that bang node: ham thuan + escape."""

    def test_pure_functions(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("khong co `node` tren PATH")
        harness = os.path.join(HERE, "ec_chat_harness.js")
        out = subprocess.run([node, harness], capture_output=True, text=True, cwd=HERE)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ALL OK", out.stdout)


if __name__ == "__main__":
    unittest.main()
