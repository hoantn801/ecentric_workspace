# Copyright (c) 2026, eCentric and contributors
"""Trang chu v2 la NGUON trang (NHIEU_LOP giai doan 2, 29/09/2026).

Truoc: server gui bo cuc CU, roi khoi JS `ec-home-v2` dung lai DOM sau khi tai va do trang
de gan lop gon -> nguoi dung thay trang cu nhay sang trang moi. Bo test nay khoa:
  1. nguon trang: byte sach, sha khop page_sync, Jinja render duoc (nguoi dung that + Guest);
  2. bo cuc v2 nam SAN trong markup; bo cuc cu da di; moi moc widget con dung cho;
  3. khong con JS dung lai bo cuc: nac gon la @container/@media, khoi <script|style id="ec-...">
     khong tang (A65);
  4. ec_home_v2.js chi do du lieu - chay THAT trong jsdom neu may co node + jsdom.
Chay khong can bench. Thieu jinja2 / node / jsdom thi test lien quan SKIP kem ly do (skip
khong phai xanh).
"""
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
SRC = os.path.join(APP, "legacy_pages", "home", "main_section.html")
JS = os.path.join(APP, "public", "js", "ec_home_v2.js")
BUNDLE = os.path.join(APP, "public", "js", "ec_home_v2.bundle.js")
HARNESS = os.path.join(HERE, "home_v2_harness.js")
LIVE_BEFORE = "2a4c6826a8f091a203a960e44be652dea97486f5ad75fef09188294e5c9bcf76"


def _src():
    with io.open(SRC, encoding="utf-8") as fh:
        return fh.read()


def _page_sync():
    """page_sync that bang frappe stub (khong can bench)."""
    if "frappe" not in sys.modules:
        stub = types.ModuleType("frappe")
        stub.whitelist = lambda *a, **k: (lambda f: f)
        stub._ = lambda s: s
        sys.modules["frappe"] = stub
    sys.path.insert(0, REPO)
    import importlib
    return importlib.import_module("ecentric_workspace.legacy_pages.home.page_sync")


# --------------------------------------------------------------------- Jinja render ----
class _NS(dict):
    __getattr__ = dict.__getitem__


def render(src, user="hoan.tran@ecentric.vn", full_name="Hoàn Trần", now=None,
           news=None, policies=None, pm=True):
    """Render nhu Frappe (SandboxedEnvironment), frappe gia. StrictUndefined: bien la nao
    trong template cung lam test DO (Frappe that dung DebugUndefined - loi bi giau)."""
    import jinja2
    from jinja2.sandbox import SandboxedEnvironment
    now = now or datetime.datetime(2026, 9, 29, 14, 23, 5)

    def get_value(dt, name, fields=None, as_dict=False):
        if dt == "User":
            if as_dict:
                return _NS(name=name, full_name=full_name, user_image=None, email=name,
                           first_name=full_name.split()[0], last_name="")
            return "System User"
        return None

    frappe = _NS(session=_NS(user=user),
                 db=_NS(get_value=get_value, exists=lambda *a, **k: True),
                 get_all=lambda dt, **k: (news or []) if dt == "News Post" else (policies or []),
                 utils=_NS(now_datetime=lambda: now))
    env = SandboxedEnvironment(undefined=jinja2.StrictUndefined)
    # has_pm_module_access: ham Jinja cua app (hooks.py jinja.methods) - o day gia lap ket qua
    return env.from_string(src).render(
        frappe=frappe, has_pm_module_access=lambda user=None: pm,
        bundled_asset=lambda p: "/assets/ecentric_workspace/dist/js/" + p)


def _jinja_or_skip(tc):
    try:
        import jinja2  # noqa: F401
    except ImportError:
        tc.skipTest("thieu jinja2 (python -m pip install jinja2)")


class TestSourceFile(unittest.TestCase):
    def test_clean_bytes(self):
        raw = io.open(SRC, "rb").read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM")
        self.assertNotIn(b"\r\n", raw, "CRLF: sha tren Windows se lech voi sha tren site")
        txt = raw.decode("utf-8")
        for mk in ("Ã", "Ä", "â€", "á»"):
            self.assertNotIn(mk, txt, "mojibake %r" % mk)
        self.assertIn("Chào buổi sáng", txt)

    def test_baseline_pins_this_file(self):
        ps = _page_sync()
        sha = hashlib.sha256(io.open(SRC, "rb").read()).hexdigest()
        self.assertEqual(ps.BASELINE_SHA256, sha, "sua main_section.html thi phai bump BASELINE_SHA256")
        self.assertEqual(ps._html(), _src(), "_html() phai tra dung file")
        self.assertIn(LIVE_BEFORE, ps.SUPERSEDES_SHA256, "ban live truoc giai doan 2 phai duoc chap nhan")
        self.assertNotIn(ps.BASELINE_SHA256, ps.SUPERSEDES_SHA256)

    def test_resync_manifest_and_patch(self):
        man = json.load(io.open(os.path.join(APP, "approval_center", "patches", "resync_manifest.json"),
                                encoding="utf-8"))
        rec = man["legacy_pages/home/main_section.html"]
        self.assertEqual(rec["sha256"], hashlib.sha256(io.open(SRC, "rb").read()).hexdigest())
        patch = os.path.join(APP, "approval_center", "patches", rec["last_resync_patch"] + ".py")
        self.assertTrue(os.path.isfile(patch))
        src = io.open(patch, encoding="utf-8").read()
        self.assertIn("page_sync.sync()", src)
        self.assertIn("except Exception", src, "patch nem loi = chan ca dot deploy")
        listed = io.open(os.path.join(APP, "patches.txt"), encoding="utf-8").read()
        self.assertIn("approval_center.patches." + rec["last_resync_patch"], listed)
        # p224 (ban dau) la patch go /home-v2 - van phai con va duoc khai
        p224 = io.open(os.path.join(APP, "approval_center", "patches", "p224_resync_home_v2_nguon.py"),
                       encoding="utf-8").read()
        self.assertIn('{"route": "home-v2"}', p224)
        self.assertIn("approval_center.patches.p224_resync_home_v2_nguon", listed)


class TestJinjaRender(unittest.TestCase):
    def setUp(self):
        _jinja_or_skip(self)

    def test_renders_for_a_real_user(self):
        out = render(_src())
        self.assertNotIn("{{", out)
        self.assertNotIn("{%", out)
        self.assertIn('<h1 id="greeting">Chào buổi chiều, Hoàn 👋</h1>', out)
        self.assertIn('<p id="today-text">Thứ Ba, 29 tháng 9</p>', out)
        self.assertIn('id="clock">14:23:05</div>', out)
        self.assertIn('class="ec2-nowpin" style="left:63.8%"', out)
        self.assertIn('<script src="/assets/ecentric_workspace/dist/js/ec_home_v2.bundle.js" defer></script>', out)

    def test_time_boundaries(self):
        cases = [
            (datetime.datetime(2026, 9, 27, 7, 59), "Chào buổi sáng", "Chủ Nhật, 27 tháng 9", "left:0%"),
            (datetime.datetime(2026, 10, 5, 12, 0), "Chào buổi chiều", "Thứ Hai, 05 tháng 10", "left:40.0%"),
            (datetime.datetime(2026, 10, 10, 18, 0), "Chào buổi tối", "Thứ Bảy, 10 tháng 10", "left:100.0%"),
            (datetime.datetime(2026, 12, 31, 23, 30), "Chào buổi tối", "Thứ Năm, 31 tháng 12", "left:100%"),
        ]
        for now, greet, day, pin in cases:
            out = render(_src(), now=now)
            self.assertIn(greet + ", Hoàn", out, now)
            self.assertIn('<p id="today-text">%s</p>' % day, out, now)
            self.assertIn('class="ec2-nowpin" style="%s"' % pin, out, now)

    def test_first_name_is_escaped(self):
        out = render(_src(), full_name='<img src=x onerror=alert(1)> B')
        self.assertIn("&lt;img", out)
        self.assertNotIn("<img src=x", out)

    def test_timeline_initial_state_by_pm_access(self):
        """Nguoi co quyen PM: 'dang tai lich' (du chieu cao, su kien ve khong day luoi);
        khong co quyen: the phang ngay tu dau (khong bao gio co lich de ve)."""
        pm = render(_src(), pm=True)
        self.assertIn('<div class="panel ec2-tl" data-ec2-tl-loading="1">', pm)
        self.assertIn('<span class="ec2-tlempty">Đang tải lịch hôm nay…</span>', pm)
        no = render(_src(), pm=False)
        self.assertIn('<div class="panel ec2-tl ec2-tlflat">', no)
        self.assertNotIn("data-ec2-tl-loading", no.split('<div class="panel ec2-tl')[1][:200])
        self.assertIn("Hôm nay chưa có họp hay việc đã xếp giờ — sự kiện sẽ hiện ở đây.</span>", no)
        # ham PM la ham cua app, khai trong hooks.py (khong chep luat quyen vao HTML)
        hooks = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertIn('"ecentric_workspace.pm.permissions.has_pm_module_access",', hooks)
        self.assertIn("{% set ec_pm = has_pm_module_access() if has_pm_module_access is defined else false %}", _src())

    def test_renders_without_the_pm_jinja_hook(self):
        """Rollback code ma chua tra trang ve ban cu: ham Jinja cua app chua co -> trang van
        render (the phang), khong phai trang chu 500 cho ca cong ty."""
        import jinja2
        from jinja2.sandbox import SandboxedEnvironment
        src = _src()
        env = SandboxedEnvironment(undefined=jinja2.DebugUndefined)   # nhu Frappe that
        frappe = render.__globals__["_NS"](
            session=_NS(user="a@b.c"), db=_NS(get_value=lambda *a, **k: None, exists=lambda *a, **k: False),
            get_all=lambda *a, **k: [], utils=_NS(now_datetime=lambda: datetime.datetime(2026, 9, 29, 9, 0)))
        out = env.from_string(src).render(frappe=frappe, bundled_asset=lambda p: "/x/" + p)
        self.assertIn('<div class="panel ec2-tl ec2-tlflat">', out)

    def test_guest_render_redirects(self):
        out = render(_src(), user="Guest")
        self.assertIn("window.location.href = '/login?redirect-to=/'", out)

    def test_news_loop_still_renders(self):
        n = _NS(name="N1", title="Tin A", category="SỰ KIỆN", image=None,
                published_on=datetime.date(2026, 9, 1))
        out = render(_src(), news=[n])
        self.assertIn('href="/app/news-post/N1" class="news-card"', out)
        self.assertIn("01/09/2026", out)

    def test_only_intended_jinja_expressions(self):
        exprs = set(re.findall(r"\{\{(.*?)\}\}", _src()))
        want = {" ec_greet ", " first_name|e ", " ec_today ", " ec_now.strftime('%H:%M:%S') ",
                " ec_pin|round(1) ", " bundled_asset('ec_home_v2.bundle.js') ",
                # vong lap tin / chinh sach / panel viec (an) - co tu ban live, giu nguyen
                " n.name ", " n.image ", " loop.index ", " n.title[:40] ", " n.category or 'TIN' ",
                " n.title ", " n.published_on.strftime('%d/%m/%Y') if n.published_on else '' ",
                " so_count ", " leave_count ", " p.name ", " p.title "}
        self.assertEqual(exprs - want, set(), "bieu thuc Jinja moi chua duoc duyet")


class TestStaticLayout(unittest.TestCase):
    """Trang thai dau nam trong markup (A65): bo cuc v2 co san, khong cho JS dung lai."""

    def test_v2_layout_is_in_markup(self):
        s = _src()
        once = ['class="content ec2-home" data-ec2-home="1"', '<section class="ec2-band"',
                'class="ec2-bandrow"', 'data-ec2-ring="1"', 'class="ec2-chips"',
                'class="ec2-grid"', 'class="panel ec2-queue"',
                'class="stat-card s-green" data-ec-sla-card="slot"']
        for mk in once:
            self.assertEqual(s.count(mk), 1, mk)
        self.assertEqual(s.count('<div class="ec2-col">'), 2)
        self.assertEqual(len(re.findall(r'<div class="stat-card s-', s)), 4)

    def test_old_layout_is_gone(self):
        s = _src()
        for mk in ('class="stats-strip"', 'class="bento"', 'class="col-left"', 'class="col-right"',
                   'id="ck-date"', 'checkin-label ec-att-head', "Cần cài Frappe HR",
                   "coming-soon?tool=cham-cong", ".ec-sb-link"):
            self.assertNotIn(mk, s, mk)

    def test_widget_anchors_kept(self):
        s = _src()
        for mk in ('data-ec-att-hours="1"', 'data-ec-leave-bal="1"',
                   '<div class="stat-value" data-ec-ac-kpi="approval">—</div>',
                   'data-ec-ac-kpi-meta="1"', '<span class="badge b-pink" data-ec-ac-badge="1" hidden></span>',
                   '<div class="checkin-status">', '<span class="status-dot-w"></span>',
                   '<button class="btn-checkin" onclick="ecentricCheckin()" disabled>Đang tải…</button>',
                   'id="clock"', 'id="greeting"', 'id="today-text"',
                   '<div class="panel" data-ec2-hidden="1">', '<div class="panel" data-ec2-cal-off="1">',
                   '<div class="panel-title">Lịch hôm nay</div>', '<div class="panel-title">Truy cập nhanh</div>',
                   'Tin nội bộ', 'Chính sách &amp; Quy định'.replace("&amp;", "&"),
                   '<button class="ec-chat-fab ec2-mascot" id="ec-chat-fab"',
                   'class="ec2-qn" hidden', '<div class="ec2-qempty">Đang tải…</div>'):
            self.assertIn(mk, s, mk)
        # panel "Viec can lam" (an) van la noi widget Action Center tim de do so CHO DUYET
        work = s[s.index('<div class="panel" data-ec2-hidden="1">'):]
        self.assertIn("Việc cần làm", work[:400])
        cal = s[s.index('<div class="panel" data-ec2-cal-off="1">'):]
        self.assertIn("Lịch hôm nay", cal[:300])

    def test_scripts_and_loaders_kept(self):
        s = _src()
        for mk in ('src="/assets/ecentric_workspace/js/action_center_widget.js" defer',
                   'src="/assets/ecentric_workspace/js/pm_home_calendar.js" defer',
                   'src="/assets/ecentric_workspace/js/sla_home_card.js" defer',
                   '"ec_hr_attendance_data"', '"/api/method/ec_hr_leave_data"',
                   '<script id="ec-chatbot-js">', '<script id="ec-csrf-fetch-patch">',
                   "<!-- CP_REDIRECT_GUARD_START -->",
                   "<script src=\"{{ bundled_asset('ec_home_v2.bundle.js') }}\" defer></script>"):
            self.assertIn(mk, s, mk)
        self.assertIn('import "./ec_home_v2.js";', io.open(BUNDLE, encoding="utf-8").read())
        # hydrate chay SAU widget lich (defer theo thu tu tai lieu) de dat co truoc khi no ve
        self.assertLess(s.index('src="/assets/ecentric_workspace/js/pm_home_calendar.js"'),
                        s.index("bundled_asset('ec_home_v2.bundle.js')"))

    def test_no_global_counts_no_unused_queries(self):
        s = _src()
        self.assertNotIn("frappe.db.count(", s)
        for dead in ("{% set initials", "{% set is_system_user"):
            self.assertNotIn(dead, s)

    def test_no_js_relayout(self):
        s = _src()
        self.assertNotIn('id="ec-home-v2', s)
        self.assertNotIn('id="ec-home-polish', s)
        self.assertIsNone(re.search(r"\.ecentric-app\.ec2-(bw|fit)\d", s), "lop gon do JS gan da bo")
        self.assertIn("container:ec2band/inline-size", s)
        for q in ("@container ec2band (max-width:1273px)", "@container ec2band (max-width:1219px)",
                  "@container ec2band (max-width:1176px)", "@container ec2band (max-width:1009px)",
                  "@media (max-height:1080px)", "@media (max-height:1000px)"):
            self.assertIn(q, s, q)
        self.assertIn("html{scrollbar-gutter:stable}", s)

    def test_a65_no_new_injected_blocks(self):
        ids = set(re.findall(r'<(?:script|style)\b[^>]*\bid="(ec-[^"]+)"', _src()))
        # dung tap khoi da co tren live truoc 29/09, TRU hai khoi da gop vao nguon
        # (ec-home-polish, ec-home-v2). Them khoi moi = vi pham A65.
        self.assertEqual(ids, {"ec-csrf-fetch-patch", "ec-action-center-widget", "ec-lich-hom-nay-loader",
                               "ec-sla-home-card-loader", "ec-chatbot-style", "ec-chatbot-js"})

    def test_cascade_order_kept(self):
        """Mot stylesheet: @import dau tien, CSS trang -> polish -> v2 (thu tu cua live)."""
        s = _src()
        a = s.index("@import url('https://fonts.googleapis.com/css2?family=Inter")
        end = s.index("</style>", a)
        css = s[a:end]
        self.assertLess(css.index(".ecentric-app .stat-card {"), css.index(".stat-card{padding:10px 12px !important;"))
        self.assertLess(css.index(".stat-card{padding:10px 12px !important;"), css.index(".ecentric-app .ec2-band{"))
        self.assertLess(css.index(".ecentric-app .ec2-band{"), css.index("@container ec2band (max-width:1273px)"))
        self.assertLess(css.index("@media (max-height:1000px)"), css.index(".ec2-tlbody.ec2-hasev{height:max("))

    def test_polish_zone_contract(self):
        """Hop dong cu cua khoi polish (22/07), nay la mot doan trong stylesheet."""
        s = _src()
        a = s.index("/* ---- polish")
        z = s[a:s.index("/* ---- v2: dai navy", a)]
        for sel in (".stat-card", ".panel", ".quick-item", ".checkin-card",
                    ".ecentric-app .ec-shell-item{padding:6px 12px", ".ecentric-app .ec-shell-grouplabel{padding:7px 12px 3px",
                    ".ecentric-app .ec-shell-head{", ".ecentric-app .ec-shell-foot{"):
            self.assertIn(sel, z, sel)
        self.assertNotIn("display:none", z)
        for decl in ("overflow:hidden", "overflow-y:hidden", "overflow-x:hidden"):
            self.assertNotIn(decl, z)
        for m in re.finditer(r"font-size:(\d+(?:\.\d+)?)px", z):
            self.assertGreaterEqual(float(m.group(1)), 11.0, m.group(0))

    def test_checkin_button_never_wraps(self):
        """29/09 10:20 tren live (man 14"): nhan "Da cham cong hom nay" rong 147,23 px > min-width
        147 px -> nut xuong 2 dong, dai navy cao them 17 px sau khi du lieu ve (p225 sua)."""
        s = _src()
        self.assertRegex(s, r"\.ecentric-app \.ec2-band \.btn-checkin\{[^}]*white-space:nowrap")
        self.assertIn(".ecentric-app .ec2-home .ec2-band .checkin-card{width:262px}", s)

    def test_mascot_is_static(self):
        s = _src()
        self.assertIn('#ec-chat-fab.ec2-mascot{background-image:url("data:image/svg+xml,', s)
        self.assertNotIn("__MASCOT", s)


class TestHydrateJs(unittest.TestCase):
    def test_static_rules(self):
        raw = io.open(JS, encoding="utf-8").read()
        # bo chu thich (chu thich duoc phep KE LAI ban cu; code thi khong duoc dung lai no)
        js = "\n".join(re.sub(r"\s//\s.*$", "", ln) for ln in raw.splitlines()
                       if not ln.lstrip().startswith("//"))
        js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        for tok in ("{{", "{%", "{#", "`", "=>"):
            self.assertFalse(tok in js, tok)
        # do-roi-gan-lop la thu giai doan 2 da bo
        for banned in ("scrollHeight", "offsetTop", "requestAnimationFrame", ".style.display",
                       "insertBefore", "ec2-fit", "ec2-bw", "document.body.appendChild",
                       "createElement('style')", "sweepTl", "MutationObserver(function () { sweep"):
            self.assertFalse(banned in js, banned)
        self.assertEqual(sorted(set(re.findall(r"classList\.(\w+)\('([\w-]+)'", js))),
                         [("toggle", "ec2-hasev"), ("toggle", "ec2-tlflat")])
        for m in re.finditer(r"addEventListener\('resize', (\w+)", js):
            self.assertEqual(m.group(1), "placeCalPop", "resize chi de dat lai popover dang mo")
        self.assertIn("window.ecTimelineOwnsEvents = true", js)
        self.assertIn("shareMs: 15000", js)

    def test_in_jsdom(self):
        _jinja_or_skip(self)
        node = shutil.which("node")
        if not node:
            self.skipTest("khong co node")
        if subprocess.run([node, "-e", "require('jsdom')"], capture_output=True, cwd=HERE).returncode:
            self.skipTest("khong nap duoc jsdom (NODE_PATH?)")
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as fh:
            fh.write(render(_src()))
            path = fh.name
        try:
            p = subprocess.run([node, HARNESS, path, JS], capture_output=True, text=True,
                               cwd=HERE, timeout=90)
        finally:
            os.unlink(path)
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
        r = json.loads(p.stdout)
        m = r["main"]
        self.assertTrue(m["owns"])
        self.assertEqual(m["hydrated"], "1")
        self.assertEqual(m["calls"], [{"m": "ecentric_workspace.action_center.api.get_reminder_summary",
                                       "a": None, "o": {"shareMs": 15000}}])
        self.assertEqual(m["ringBefore"], "—")
        self.assertEqual(m["ringEm"], m["expectRing"])
        self.assertTrue(m["ringB"].startswith("12 / "))
        self.assertEqual(m["qi"], 6)                     # 2 gap + 1 dang xu ly + 3/4 sap toi
        self.assertEqual(m["qg"], ["GẤP", "ĐANG XỬ LÝ", "SẮP TỚI"])
        self.assertEqual(m["qBadge"], {"text": "7", "hidden": False})
        self.assertEqual(m["hot"], [" — 2 việc gấp đang chờ"])
        self.assertIn("&lt;b&gt;PO&lt;/b&gt;", m["qHtml"])  # du lieu duoc escape
        self.assertIn('href="/approvals/x?a=1&amp;b=2"', m["qHtml"])
        self.assertEqual([e["t"] for e in m["ev"]], ["Họp giao ban", "Review <x>", "Viết spec"])
        self.assertEqual([e["l"] for e in m["ev"]], ["0", "1", "0"])   # hai hop chong gio -> 2 lan
        self.assertEqual(m["lanes"], "2")
        self.assertEqual([e["b"] for e in m["ev"]], [False, False, True])
        self.assertEqual((m["tlLoading0"], m["tlFlat0"]), ("1", False))   # nguoi co quyen PM
        self.assertEqual((m["flat"], m["hasev"]), (False, True))
        self.assertEqual((m["popOpen"], m["popAfter"]), ("1", None))
        self.assertEqual((m["flatAgain"], m["evAgain"]), (True, 0))
        self.assertEqual(m["emptyTxt"], "Hôm nay chưa có họp hay việc đã xếp giờ — sự kiện sẽ hiện ở đây.")
        self.assertIsNone(m["tlLoadingEnd"])
        # BO CUC KHONG DOI: khong phan tu nao cua dai navy / dong thoi gian / luoi bi tao, xoa,
        # doi cho, doi lop (tru ec2-tlflat/ec2-hasev); khong ghi style.display; khong lop tren app
        self.assertTrue(m["skeletonSame"], m.get("skeletonDiff"))
        self.assertEqual(m["displayWrites"], 0)
        self.assertEqual(m["appClasses"], "ecentric-app")
        # chay hai lan = mot lan
        self.assertEqual(r["twice"]["qi"], 6)
        self.assertEqual(len(r["twice"]["calls"]), 1)
        # API hong -> bao loi, khong ve gi khac
        self.assertEqual(r["fail"]["qEmpty"], "Không tải được danh sách việc.")
        self.assertTrue(r["fail"]["qBadge"]["hidden"])
        # khong co ecApi (bundle chua nap) -> fetch thang, van ve duoc
        self.assertEqual(r["noApi"]["calls"], [{"fetch": "/api/method/ecentric_workspace.action_center.api.get_reminder_summary"}])
        self.assertEqual(r["noApi"]["qEmpty"], "Bạn không có việc nào cần xử lý. 🎉")


if __name__ == "__main__":
    unittest.main()
