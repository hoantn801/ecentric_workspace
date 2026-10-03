# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo v6 (mockup v6, PO duyet 03/10/2026) - chay THAT tren repo gia:
hen gio dang, gui kem Teams, AI viet giup, loc anh AI dinh chu, binh luan, xac nhan da doc.

    python -m unittest ecentric_workspace.internal_posts.tests.test_v6
"""
import datetime as dt
import io
import json
import os
import sys
import types
import unittest

from ecentric_workspace.internal_posts import ack as A
from ecentric_workspace.internal_posts import ai_write as W
from ecentric_workspace.internal_posts import comments as CM
from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import cover_ai as AI
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts import editor_service as E
from ecentric_workspace.internal_posts import schedule as SCH
from ecentric_workspace.internal_posts import service as S
from ecentric_workspace.internal_posts.tests.test_internal_posts import (
    APP, EVIL, HR, LAN, MINH, NOEMP, TODAY, TU, Doc, FakeRepo, _env, _render, payload, seeded)


def _sched(**kw):
    base = dict(publish_mode="schedule", publish_date="2026-10-05", publish_time="08:30")
    base.update(kw)
    return payload(**base)


# ====================================================================== domain ===
class TestDomainV6(unittest.TestCase):
    def test_time_labels(self):
        at = dt.datetime(2026, 10, 5, 8, 30)
        self.assertEqual(D.when_label(at), "08:30 thứ Hai 05/10")
        self.assertEqual(D.short_when("2026-10-06 08:30:00"), "08:30 · T3 06/10")
        self.assertEqual(D.short_when(dt.datetime(2026, 10, 4, 9, 0)), "09:00 · CN 04/10")
        now = dt.datetime(2026, 10, 6, 10, 0)
        self.assertEqual(D.ago(now - dt.timedelta(seconds=20), now), "vừa xong")
        self.assertEqual(D.ago(now - dt.timedelta(minutes=35), now), "35 phút trước")
        self.assertEqual(D.ago(now - dt.timedelta(hours=2), now), "2 giờ trước")
        self.assertEqual(D.ago(dt.datetime(2026, 10, 5, 16, 5), now), "hôm qua lúc 16:05")
        self.assertEqual(D.ago(dt.datetime(2026, 9, 28, 9, 0), now), "28/09")

    def test_check_schedule_and_dates(self):
        now = dt.datetime(2026, 10, 1, 9, 0)
        self.assertEqual(D.check_schedule("2026-10-06 08:30", now), "")
        self.assertIn("đã qua", D.check_schedule("2026-10-01 08:59", now))
        self.assertIn("60 ngày", D.check_schedule("2027-01-01 08:00", now))
        self.assertIn("Chọn ngày", D.check_schedule("", now))
        self.assertEqual(D.check_dates({"publish_at": "2026-10-06 08:30", "expires_on": "2026-10-05"}, TODAY),
                         ["Ngày hết hạn đang trước ngày hẹn đăng."])
        self.assertEqual(D.check_dates({"require_ack": 1}, TODAY), ["Chọn hạn xác nhận đã đọc."])
        self.assertEqual(D.check_dates({"require_ack": 1, "ack_deadline": "2026-10-05",
                                        "publish_at": "2026-10-06 08:00"}, TODAY),
                         ["Hạn xác nhận phải từ ngày bài lên trở đi."])
        self.assertEqual(D.check_dates({"require_ack": 1, "ack_deadline": "2026-10-13",
                                        "publish_at": "2026-10-06 08:00"}, TODAY), [])

    def test_ack_reminder_days(self):
        self.assertEqual(D.ack_remind_dates("2026-10-13"), [dt.date(2026, 10, 12), dt.date(2026, 10, 13)])
        self.assertTrue(D.ack_remind_due("2026-10-13", dt.date(2026, 10, 12)))
        self.assertFalse(D.ack_remind_due("2026-10-13", dt.date(2026, 10, 11)))
        self.assertEqual(D.ack_days_left("2026-10-08", TODAY), "còn 7 ngày")
        self.assertEqual(D.ack_days_left("2026-10-01", TODAY), "hôm nay là hạn")
        self.assertEqual(D.ack_days_left("2026-09-29", TODAY), "quá hạn 2 ngày")


# ====================================================================== 1. hen gio =
class TestSchedule(unittest.TestCase):
    def test_schedule_save_and_guards(self):
        r = seeded()
        res = E.save(HR, _sched(), "publish", repo=r)
        p = r.posts[res["name"]]
        self.assertEqual((p["published"], p["publish_at"]), (0, dt.datetime(2026, 10, 5, 8, 30)))
        self.assertTrue(res["scheduled"])
        self.assertEqual(res["publish_at_label"], "08:30 thứ Hai 05/10")
        with self.assertRaises(S.PostError):
            E.save(HR, _sched(publish_date="2026-10-01", publish_time="08:00"), "publish", repo=r)
        with self.assertRaises(S.PostError):
            E.save(HR, _sched(publish_date="2026-12-31"), "publish", repo=r)
        # "Luu nhap" tren bai hen = bo hen
        E.save(HR, _sched(name=res["name"]), "save", repo=r)
        self.assertIsNone(r.posts[res["name"]]["publish_at"])
        # "Dang ngay" (khong hen) tren bai nhap: dang + xoa hen
        E.save(HR, _sched(name=res["name"]), "publish", repo=r)
        E.save(HR, payload(name=res["name"], publish_mode="now"), "publish", repo=r)
        self.assertEqual((r.posts[res["name"]]["published"], r.posts[res["name"]]["publish_at"]), (1, None))

    def test_compose_context_round_trip(self):
        r = seeded()
        name = E.save(HR, _sched(notify_teams=1, require_ack=1, ack_deadline="2026-10-13", allow_comments=0),
                      "publish", repo=r)["name"]
        post = E.compose_context(HR, name, repo=r)["post"]
        self.assertEqual((post["scheduled"], post["publish_date"], post["publish_time"]), (True, "2026-10-05", "08:30"))
        self.assertEqual((post["notify_teams"], post["require_ack"], post["ack_deadline"], post["allow_comments"]),
                         (True, True, "2026-10-13", False))

    def test_manage_tab_and_publish_now(self):
        r = seeded()
        name = E.save(HR, _sched(notify_teams=1), "publish", repo=r)["name"]
        ctx = E.manage_context(HR, "scheduled", repo=r)
        self.assertEqual({t["key"]: t["count"] for t in ctx["tabs"]}["scheduled"], 1)
        row = ctx["items"][0]
        self.assertEqual((row["publish_at_label"], row["channels"]), ("08:30 · T2 05/10", "Chuông · Teams · Popup"))
        self.assertNotIn(name, [i["name"] for i in E.manage_context(HR, "draft", repo=r)["items"]])
        with self.assertRaises(S.Forbidden):
            E.publish_now(LAN, name, repo=r)
        E.publish_now(HR, name, repo=r)
        self.assertEqual((r.posts[name]["published"], r.posts[name]["publish_at"]), (1, None))
        out = _render("quan_ly", E.manage_context(HR, "scheduled", repo=r))
        self.assertIn("Chưa có bài nào hẹn giờ", out)

    def test_publish_due_job(self):
        r = seeded()
        due = E.save(HR, _sched(title="Tới giờ"), "publish", repo=r)["name"]
        later = E.save(HR, _sched(title="Chưa tới", publish_time="17:00"), "publish", repo=r)["name"]
        bad = E.save(HR, _sched(title="Hỏng"), "publish", repo=r)["name"]
        r.clock = dt.datetime(2026, 10, 5, 8, 34)
        r.fail_save = bad
        out = SCH.publish_due(repo=r)
        self.assertEqual(out["published"], [due])
        self.assertEqual(out["failed"], [bad])
        self.assertEqual((r.posts[due]["published"], r.posts[due]["publish_at"]), (1, None))
        self.assertEqual(r.posts[later]["published"], 0)
        self.assertIsNone(r.posts[bad]["publish_at"], "loi -> bo hen, khong thu lai moi 5 phut")
        self.assertEqual(r.bells[-1][1], HR)
        self.assertIn("chưa đăng được", r.bells[-1][2])
        self.assertNotIn("/app", r.bells[-1][4])
        self.assertEqual(SCH.publish_due(repo=r), {"published": [], "failed": []}, "chay lai: khong lam gi")

    def test_post_page_shows_schedule_to_hr(self):
        r = seeded()
        name = E.save(HR, _sched(title="Lịch nghỉ Tết"), "publish", repo=r)["name"]
        slug = r.posts[name]["slug"]
        page = S.post_page(HR, slug, repo=r)
        out = _render("bai", {"post": page})
        self.assertIn("Đã hẹn đăng lúc 08:30 thứ Hai 05/10", out)
        self.assertIn("08:30 · T2 05/10", out)
        self.assertIn("05/10 – 11/10", out, "popup 7 ngay tinh tu luc bai len")
        with self.assertRaises(S.Forbidden):
            S.post_page(LAN, slug, repo=r)


# ====================================================================== 2. Teams ===
class TestScheduleRetry(unittest.TestCase):
    def test_transient_error_keeps_schedule_then_gives_up(self):
        r = seeded()
        n = E.save(HR, _sched(title="Khoá DB"), "publish", repo=r)["name"]
        n2 = E.save(HR, _sched(title="Hỏng mãi", publish_time="09:00"), "publish", repo=r)["name"]
        r.fail_save = None
        r.fail_transient = n
        r.clock = dt.datetime(2026, 10, 5, 8, 35)
        self.assertEqual(SCH.publish_due(repo=r)["failed"], [n])
        self.assertIsNotNone(r.posts[n]["publish_at"], "loi tam thoi: giu hen, lan sau thu lai")
        self.assertEqual(r.bells, [])
        r.fail_transient = None
        self.assertEqual(SCH.publish_due(repo=r)["published"], [n])
        r.fail_transient = n2
        r.clock = dt.datetime(2026, 10, 5, 15, 30)
        SCH.publish_due(repo=r)
        self.assertIsNone(r.posts[n2]["publish_at"], "qua 6 gio van hong: bo hen + bao")
        self.assertEqual(r.bells[-1][1], HR)


class TestTeams(unittest.TestCase):
    def test_teams_needs_bell(self):
        r = seeded()
        n = E.save(HR, payload(notify_teams=1), repo=r)["name"]
        self.assertEqual(r.posts[n]["notify_teams"], 1)
        E.save(HR, payload(name=n, notify_teams=1, notify_bell=0), repo=r)
        self.assertEqual(r.posts[n]["notify_teams"], 0, "tat chuong thi Teams tat theo")
        n2 = E.save(HR, payload(), repo=r)["name"]
        self.assertEqual(r.posts[n2]["notify_teams"], 0, "mac dinh TAT")

    def test_notify_uses_urgent_event_only_when_ticked(self):
        sent = []
        fake_events = types.ModuleType("ecentric_workspace.notification_center.events")
        fake_events.publish_notification_event = lambda ev, user, title, msg, **kw: sent.append((ev, user, title, msg))
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.logger = lambda *a: types.SimpleNamespace(info=lambda *x: None)
        saved = {k: sys.modules.get(k) for k in ("frappe", "ecentric_workspace.notification_center.events",
                                                 "ecentric_workspace.internal_posts.notify",
                                                 "ecentric_workspace.internal_posts.repository")}
        sys.modules["frappe"] = fake_frappe
        sys.modules["ecentric_workspace.notification_center.events"] = fake_events
        sys.modules["ecentric_workspace.internal_posts.repository"] = types.ModuleType("repo_stub")
        sys.modules.pop("ecentric_workspace.internal_posts.notify", None)
        try:
            from ecentric_workspace.internal_posts import notify as N
            r = seeded()
            r.posts["P1"].update(notify_teams=1, push_to_home=0, require_ack=1, ack_deadline=dt.date(2026, 10, 8))
            r.posts["P2"].update(notify_teams=0, push_to_home=0)
            N.R = r
            N.run("P1")
            N.run("P2")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        p1 = [s for s in sent if s[2].endswith("Kế hoạch team building")]
        p2 = [s for s in sent if s[2] == "Quy chế công tác phí"]
        self.assertTrue(p1 and p2)
        self.assertEqual({s[0] for s in p1}, {"announcement_urgent"})
        self.assertEqual({s[0] for s in p2}, {"announcement"})
        self.assertTrue(p1[0][2].startswith("Cần xác nhận đã đọc: "))
        self.assertIn("Hạn xác nhận 08/10/2026", p1[0][3])


# ====================================================================== 3. AI viet =
GOOD = {"title": "Ban hành Quy chế công tác phí, phiên bản 2.",
        "summary": "Áp dụng từ 15/10/2026.",
        "sections": [{"heading": "Điểm thay đổi chính", "intro": "", "items": ["Lưu trú 900.000 ₫", EVIL]},
                     {"heading": "Các bước", "intro": "Làm như sau", "items": ["Mở ERP", "Tạo phiếu"], "ordered": True}]}


class TestAIWrite(unittest.TestCase):
    def test_build_escapes_and_structures(self):
        a = W.build(GOOD)
        self.assertEqual(a["title"], "Ban hành Quy chế công tác phí, phiên bản 2")
        self.assertIn("<h2>Điểm thay đổi chính</h2><ul><li>Lưu trú 900.000 ₫</li>", a["content"])
        self.assertIn("<ol><li>Mở ERP</li><li>Tạo phiếu</li></ol>", a["content"])
        self.assertNotIn("<script>", a["content"])
        self.assertIn("&lt;script&gt;", a["content"])
        self.assertIsNone(W.build({"title": "", "sections": []}))
        self.assertIsNone(W.build({"title": "T", "sections": [{"heading": ""}]}))

    def test_write_limit_and_failures(self):
        r = seeded()
        r.ai_reply = {"ok": True, "data": GOOD}
        with self.assertRaises(S.Forbidden):
            W.write(LAN, "P1", "- y chinh mot", repo=r)
        with self.assertRaises(S.PostError):
            W.write(HR, "P1", "ngắn", repo=r)
        out = W.write(HR, "P1", "- quy chế công tác phí v2", "steps", repo=r)
        self.assertEqual((out["used"], out["limit"]), (1, 10))
        prompt, kw = r.ai_calls[-1]
        self.assertIn("Hướng dẫn từng bước", prompt)
        self.assertIn("quy chế công tác phí v2", prompt)
        self.assertEqual(kw["schema"], W.SCHEMA)
        self.assertLess(kw["budget"], 120, "goi trong request web: duoi tran 120s")
        # AI hong: khong mat luot
        r.ai_reply = {"ok": False, "error": "timeout"}
        with self.assertRaises(S.PostError) as cm:
            W.write(HR, "P1", "- quy chế công tác phí v2", repo=r)
        self.assertIn("không mất lượt", str(cm.exception))
        self.assertEqual(W.quota(HR, "P1", repo=r)["used"], 1)
        r.ai_reply = {"ok": True, "data": GOOD}
        for _ in range(9):
            W.write(HR, "P1", "- quy chế công tác phí v2", repo=r)
        with self.assertRaises(S.PostError) as cm:
            W.write(HR, "P1", "- quy chế công tác phí v2", repo=r)
        self.assertIn("10/10", str(cm.exception))
        # bai chua luu: tinh theo nguoi, quy rieng
        self.assertEqual(W.write(HR, "", "- y chinh bai moi", repo=r)["used"], 1)
        r.ai_on = False
        with self.assertRaises(S.PostError):
            W.write(HR, "P2", "- y chinh bai khac", repo=r)

    def test_compose_page_has_ai_write(self):
        r = seeded()
        ctx = E.compose_context(HR, "P1", repo=r)
        self.assertEqual(ctx["ai_write"]["limit"], 10)
        ctx.update(post_view=ctx["post"], ip_data_json="{}", ip_editor_js="/e.js", ip_aiw_js="/w.js")
        out = _render("viet_bai", ctx)
        self.assertIn("data-eip-aiw-open", out)
        self.assertIn('<option value="steps">Hướng dẫn từng bước</option>', out)
        self.assertIn('<script src="/w.js" defer></script>', out)


# ====================================================================== 4. loc anh =
class TestCoverFilter(unittest.TestCase):
    def setUp(self):
        self._avail = AI.available
        AI.available = lambda: True

    def tearDown(self):
        AI.available = self._avail

    def test_pick_rules(self):
        self.assertEqual(AI.pick([(0, True), (1, False), (2, True), (3, True)])[0], [0, 2, 3])
        keep, note = AI.pick([(0, False), (1, False)])
        self.assertEqual(keep, [])
        self.assertIn("dính chữ hoặc logo nên đã bỏ hết", note)
        keep, note = AI.pick([(0, True), (1, None), (2, False), (3, None)])
        self.assertEqual(keep, [0, 1, 3])
        self.assertIn("2 ảnh chưa soi được", note)
        keep, note = AI.pick([(0, True), (1, True), (2, True), (3, None)])
        self.assertEqual(keep, [0, 1, 2])
        self.assertEqual(note, "AI đã soi 3 ảnh, không ảnh nào dính chữ. 3 ảnh trên đều sạch.")

    def test_all_dirty_fails_with_readable_note(self):
        r = seeded()
        job = AI.start(HR, "P1", "Tiêu đề", repo=r)["job"]

        def gen(prompt, **kw):
            if kw.get("files"):
                return {"ok": True, "data": {"has_text": True, "has_logo": False}}
            return {"ok": True, "data": {"image_prompt": "abstract navy shapes without any text at all"}}

        AI.run_job(job, repo=r, generate=gen,
                   make_images=lambda p, n, **k: {"urls": ["https://k/%d.png" % i for i in range(n)]})
        st = AI.status(HR, job, repo=r)
        self.assertEqual((st["status"], st["images"]), ("Failed", []))
        self.assertIn("dính chữ hoặc logo", st["error"])
        self.assertEqual([f for f in r.files if "ai-bia" in f], [], "anh ban khong luu")

    def test_vision_down_keeps_images(self):
        r = seeded()
        job = AI.start(HR, "P1", "Tiêu đề", repo=r)["job"]

        def gen(prompt, **kw):
            if kw.get("files"):
                return {"ok": False, "error": "model khong nhan tep"}
            return {"ok": True, "data": {"image_prompt": "abstract navy shapes without any text at all"}}

        AI.run_job(job, repo=r, generate=gen,
                   make_images=lambda p, n, **k: {"urls": ["https://k/%d.png" % i for i in range(n)]})
        st = AI.status(HR, job, repo=r)
        self.assertEqual((st["status"], len(st["images"])), ("Done", 3))
        self.assertIn("chưa soi được", st["note"])


# ====================================================================== 5. binh luan
def _live_comment_post():
    r = seeded()
    r.posts["P1"]["allow_comments"] = 1
    return r


class TestComments(unittest.TestCase):
    def test_add_reply_and_notify(self):
        r = _live_comment_post()
        v = CM.add(LAN, "P1", "  Đăng ký ở đâu ạ?\nCảm ơn  ", repo=r)
        self.assertEqual(v["count"], 1)
        c1 = v["items"][0]
        self.assertEqual((c1["author"], c1["dept"], c1["ago"], c1["content"]),
                         ("Nguyễn Thị Lan", "Vận hành", "vừa xong", "Đăng ký ở đâu ạ?\nCảm ơn"))
        self.assertEqual(r.bells[-1][1], HR, "chuong cho nguoi dang bai")
        self.assertEqual(r.bells[-1][0], "announcement", "binh luan: chuong, khong Teams")
        self.assertTrue(r.bells[-1][4].endswith("/tin-noi-bo/team-building#binh-luan"))
        v = CM.add(HR, "P1", "Ở form ERP nhé", parent=c1["name"], repo=r)
        rep = v["items"][0]["replies"][0]
        self.assertTrue(rep["is_post_author"])
        self.assertEqual(r.bells[-1][1], LAN, "tra loi: chuong cho nguoi viet binh luan goc")
        # tra loi mot tra loi -> van gan vao goc
        v = CM.add(MINH, "P1", "Em cũng hỏi", parent=rep["name"], repo=r)
        self.assertEqual(len(v["items"]), 1)
        self.assertEqual(len(v["items"][0]["replies"]), 2)
        self.assertEqual({b[1] for b in r.bells[-2:]}, {LAN, HR})
        before = len(r.bells)
        CM.add(HR, "P1", "Tự bình luận bài mình", repo=r)
        self.assertEqual(len(r.bells), before, "khong gui chuong cho chinh minh")
        # nguoi duoc tra loi khong con doc duoc bai -> khong gui trich doan
        root = CM.add(TU, "P1", "Hỏi", repo=r)["items"][-1]["name"]
        r.emps = [e for e in r.emps if e["user"] != TU]
        before = len(r.bells)
        CM.add(LAN, "P1", "Đáp", parent=root, repo=r)
        self.assertNotIn(TU, [b[1] for b in r.bells[before:]])

    def test_guards(self):
        r = _live_comment_post()
        with self.assertRaises(S.PostError):
            CM.add(LAN, "P1", "   ", repo=r)
        with self.assertRaises(S.PostError):
            CM.add(LAN, "P1", "x" * (C.COMMENT_MAX_CHARS + 1), repo=r)
        with self.assertRaises(S.Forbidden):
            CM.add(TU, "P3", "ngoai pham vi", repo=r)
        with self.assertRaises(S.Forbidden):
            CM.add(NOEMP, "P1", "khong co ho so", repo=r)
        with self.assertRaises(S.Forbidden):
            CM.add(LAN, "P5", "bai nhap", repo=r)
        r.posts["P2"]["allow_comments"] = 0
        with self.assertRaises(S.PostError):
            CM.add(LAN, "P2", "tat binh luan", repo=r)
        for i in range(C.COMMENT_RATE_MAX):
            CM.add(LAN, "P1", "lần %d" % i, repo=r)
        with self.assertRaises(S.PostError) as cm:
            CM.add(LAN, "P1", "spam", repo=r)
        self.assertIn("hơi nhanh", str(cm.exception))
        r.clock += dt.timedelta(minutes=2)
        CM.add(LAN, "P1", "qua một phút gửi tiếp được", repo=r)

    def test_edit_delete_hide_like(self):
        r = _live_comment_post()
        c = CM.add(LAN, "P1", "Gốc", repo=r)["items"][0]["name"]
        rep = CM.add(MINH, "P1", "Trả lời", parent=c, repo=r)["items"][0]["replies"][0]["name"]
        with self.assertRaises(S.Forbidden):
            CM.edit(MINH, c, "sửa của người khác", repo=r)
        v = CM.edit(LAN, c, "Gốc đã sửa", repo=r)
        self.assertEqual((v["items"][0]["content"], v["items"][0]["edited"]), ("Gốc đã sửa", True))
        v = CM.like(MINH, c, repo=r)
        self.assertEqual((v["items"][0]["likes"], v["items"][0]["liked"]), (1, True))
        self.assertEqual(CM.like(MINH, c, repo=r)["items"][0]["likes"], 0)
        # HR an goc: nguoi khac khong thay ca chuoi; HR van thay + "Hien lai"
        with self.assertRaises(S.Forbidden):
            CM.hide(LAN, c, repo=r)
        v = CM.hide(HR, c, repo=r)
        self.assertTrue(v["items"][0]["hidden"])
        with self.assertRaises(S.PostError):
            CM.edit(LAN, c, "sửa bằng chứng", repo=r)
        with self.assertRaises(S.PostError):
            CM.delete(LAN, c, repo=r)
        self.assertEqual(CM.view(r, r.get_post("P1"), MINH, False)["items"], [])
        self.assertEqual(CM.view(r, r.get_post("P1"), MINH, False)["count"], 0)
        with self.assertRaises(S.PostError):
            CM.add(MINH, "P1", "trả lời bình luận đã ẩn", parent=c, repo=r)
        CM.hide(HR, c, False, repo=r)
        # xoa goc con tra loi -> "Binh luan da bi xoa"; xoa tra loi -> mat han
        with self.assertRaises(S.Forbidden):
            CM.delete(HR, c, repo=r)
        v = CM.delete(LAN, c, repo=r)
        self.assertEqual((v["items"][0]["deleted"], v["items"][0]["content"]), (True, ""))
        self.assertEqual(r.comments[c]["content"], "", "xoa that noi dung")
        v = CM.delete(MINH, rep, repo=r)
        self.assertEqual(v["items"], [])

    def test_render_escapes_and_page_block(self):
        r = _live_comment_post()
        c = CM.add(LAN, "P1", EVIL, repo=r)["items"][0]["name"]
        CM.add(HR, "P1", "ok", parent=c, repo=r)
        CM.add(MINH, "P1", "an di", repo=r)
        CM.hide(HR, "CM03", repo=r)
        env = _env()
        tpl = env.get_template("templates/includes/internal_posts/comments.html")
        out = tpl.render(cm=CM.view(r, r.get_post("P1"), MINH, False))
        self.assertNotIn(EVIL, out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn('data-eip-cmt-act="reply"', out)
        self.assertNotIn("an di", out, "nhan vien khong thay binh luan da an")
        self.assertNotIn("Ẩn bình luận", out)
        hr = tpl.render(cm=CM.view(r, r.get_post("P1"), HR, True))
        self.assertIn("Bình luận đã ẩn bởi HR", hr)
        self.assertIn('data-eip-cmt-act="unhide"', hr)
        self.assertIn("Người đăng bài", hr)
        page = _render("bai", {"post": S.post_page(LAN, "team-building", repo=r)})
        self.assertIn('id="binh-luan"', page)
        self.assertIn("Bình luận <em data-eip-cmt-count>2</em>", page)
        r.posts["P1"]["allow_comments"] = 0
        page = _render("bai", {"post": S.post_page(LAN, "team-building", repo=r)})
        self.assertIn("HR đã tắt bình luận cho bài này.", page)
        self.assertNotIn("data-eip-cmt-in", page)

    def test_manage_counts_comments(self):
        r = _live_comment_post()
        CM.add(LAN, "P1", "một", repo=r)
        CM.add(MINH, "P1", "hai", repo=r)
        CM.hide(HR, "CM02", repo=r)
        row = next(i for i in E.manage_context(HR, "live", repo=r)["items"] if i["name"] == "P1")
        self.assertEqual(row["comments"], 1)


# ====================================================================== 6. xac nhan
def _ack_post():
    r = seeded()
    r.posts["P2"].update(require_ack=1, ack_deadline=dt.date(2026, 10, 8))
    return r


class TestAck(unittest.TestCase):
    def test_view_and_ack(self):
        r = _ack_post()
        doc = r.get_post("P2")
        v = A.view(r, doc, LAN, False)
        self.assertEqual((v["total"], v["acked"], v["can_ack"], v["days_left"]), (4, 0, True, "còn 7 ngày"))
        self.assertEqual(v["not_seen_names"], [], "ten chi HR thay")
        self.assertEqual(A.view(r, r.get_post("P1"), LAN, False), None)
        d = A.ack(LAN, "P2", repo=r)
        self.assertEqual((d["first"], d["acked"], d["total"]), (True, 1, 4))
        self.assertIn(LAN, r.seen["P2"], "xac nhan thi tinh luon da xem")
        self.assertFalse(A.ack(LAN, "P2", repo=r)["first"], "bam lai khong doi gi")
        self.assertFalse(A.view(r, r.get_post("P2"), LAN, False)["can_ack"])
        hr = A.view(r, r.get_post("P2"), HR, True)
        self.assertEqual(hr["not_seen_names"], ["Lê Minh", "Phạm Tú", "Trần Hoàn"])
        with self.assertRaises(S.PostError):
            A.ack(LAN, "P1", repo=r)                       # bai khong bat buoc
        with self.assertRaises(S.PostError):
            A.ack(TU, "P3", repo=r)                        # ngoai pham vi
        r.posts["P3"].update(require_ack=1, ack_deadline=dt.date(2026, 10, 8))
        self.assertEqual(A.ack(MINH, "P3", repo=r)["total"], 2, "phong cha gom phong con")

    def test_cards_badge_until_acked(self):
        r = _ack_post()
        cards = {c["name"]: c for c in S.list_page(LAN, category="chinh-sach", repo=r)["items"]}
        self.assertTrue(cards["P2"]["need_ack"])
        out = _render("index", S.list_page(LAN, category="chinh-sach", repo=r))
        self.assertIn("Cần xác nhận trước 08/10", out)
        A.ack(LAN, "P2", repo=r)
        cards = {c["name"]: c for c in S.list_page(LAN, category="chinh-sach", repo=r)["items"]}
        self.assertFalse(cards["P2"]["need_ack"])
        r.posts["P3"].update(require_ack=1, ack_deadline=dt.date(2026, 10, 8))
        cards = {c["name"]: c for c in S.list_page(HR, repo=r)["items"] or S.list_page(HR, q="Lịch", repo=r)["items"]}
        hr_cards = {c["name"]: c for c in S.list_page(HR, q="Lịch trực", repo=r)["items"]}
        self.assertFalse(hr_cards["P3"]["need_ack"], "HR ngoai phong: khong bi doi xac nhan")
        lan_cards = {c["name"]: c for c in S.list_page(LAN, q="Lịch trực", repo=r)["items"]}
        self.assertTrue(lan_cards["P3"]["need_ack"])

    def test_remind_once_a_day(self):
        r = _ack_post()
        A.ack(LAN, "P2", repo=r)
        with self.assertRaises(S.Forbidden):
            A.remind(LAN, "P2", repo=r)
        out = A.remind(HR, "P2", repo=r)
        self.assertEqual(out["sent"], 3)
        self.assertEqual({b[1] for b in r.bells}, {HR, MINH, TU})
        self.assertTrue(all(b[0] == "announcement" for b in r.bells))
        self.assertIn("Hạn xác nhận 08/10/2026 (còn 7 ngày)", r.bells[0][3])
        with self.assertRaises(S.PostError) as cm:
            A.remind(HR, "P2", repo=r)
        self.assertIn("Hôm nay đã nhắc", str(cm.exception))

    def test_auto_reminders(self):
        r = _ack_post()
        r.posts["P1"].update(require_ack=1, ack_deadline=dt.date(2026, 10, 1))      # han hom nay
        r.posts["P4"].update(require_ack=1, ack_deadline=dt.date(2026, 10, 2))      # het han hien thi
        out = A.remind_due(repo=r)
        self.assertEqual(out["posts"], 1, "P2 con 7 ngay: chua nhac; P4 het han: bo")
        self.assertEqual(out["sent"], 4)
        self.assertEqual(A.remind_due(repo=r)["sent"], 4, "goi lai")
        self.assertEqual(len(r.bells), 4, "dedupe theo bai + nguoi + ngay")

    def test_export_rows(self):
        r = _ack_post()
        A.ack(MINH, "P2", repo=r)
        with self.assertRaises(S.Forbidden):
            A.export(LAN, "P2", repo=r)
        fname, rows = A.export(HR, "P2", repo=r)
        self.assertEqual(fname, "xac-nhan-cong-tac-phi.xlsx")
        self.assertEqual(rows[0], A.EXPORT_HEADER)
        self.assertEqual(rows[-1][0:5], ["Lê Minh", MINH, "Kho", "Có", "Có"], "nguoi chua xac nhan len truoc")
        self.assertEqual(rows[-1][5], "01/10/2026 09:00")
        r.names[TU] = "=HYPERLINK(\"http://x\")"
        self.assertTrue(any(row[0].startswith("'=") for row in A.export(HR, "P2", repo=r)[1]), "chan cong thuc Excel")
        self.assertEqual(len(rows), 5)

    def test_post_page_render(self):
        r = _ack_post()
        out = _render("bai", {"post": S.post_page(LAN, "cong-tac-phi", repo=r)})
        self.assertIn("Bài này cần bạn xác nhận đã đọc", out)
        self.assertIn("data-eip-ack", out)
        self.assertIn("0</b><span>/ 4 đã xác nhận", out)
        self.assertNotIn("CHƯA XÁC NHẬN", out)
        A.ack(LAN, "P2", repo=r)
        out = _render("bai", {"post": S.post_page(LAN, "cong-tac-phi", repo=r)})
        self.assertIn("Bạn đã xác nhận đã đọc bài này.", out)
        hr = _render("bai", {"post": S.post_page(HR, "cong-tac-phi", repo=r)})
        self.assertIn("CHƯA XÁC NHẬN · chỉ HR thấy tên", hr)
        self.assertIn("Nhắc 3 người chưa xác nhận", hr)
        self.assertIn("ack_export?post=P2", hr)
        self.assertIn("Tự nhắc: 07/10 và 08/10 lúc 09:00", hr)
        r.posts["P2"]["ack_reminded_on"] = TODAY
        hr = _render("bai", {"post": S.post_page(HR, "cong-tac-phi", repo=r)})
        self.assertIn("Hôm nay đã nhắc", hr)

    def test_manage_ack_column(self):
        r = _ack_post()
        A.ack(LAN, "P2", repo=r)
        row = next(i for i in E.manage_context(HR, "live", repo=r)["items"] if i["name"] == "P2")
        self.assertEqual(row["ack"]["label"], "1/4")
        out = _render("quan_ly", E.manage_context(HR, "live", repo=r))
        self.assertIn("1/4", out)


# ====================================================================== nen tang ==
class TestReadReceiptKinds(unittest.TestCase):
    def test_seen_key_unchanged_and_ack_separate(self):
        calls = []
        fake = types.ModuleType("frappe")
        fake.get_all = lambda dt_, filters=None, **kw: calls.append(filters) or []
        saved = sys.modules.get("frappe")
        sys.modules["frappe"] = fake
        sys.modules.pop("ecentric_workspace.platform.read_receipt", None)
        try:
            from ecentric_workspace.platform import read_receipt as RR
            self.assertEqual(RR._key("EC Internal Post", "P1", "a@x"), "EC Internal Post|P1||a@x",
                             "khoa luot xem giu dang cu - dong da co khong trung lap")
            self.assertEqual(RR._key("EC Internal Post", "P1", "a@x", kind="ack"), "EC Internal Post|P1||a@x|ack")
            RR.seen_users("EC Internal Post", "P1")
            RR.seen_users("EC Internal Post", "P1", kind=RR.ACK)
            self.assertEqual([c["kind"] for c in calls], ["seen", "ack"])
        finally:
            sys.modules.pop("ecentric_workspace.platform.read_receipt", None)
            if saved is not None:
                sys.modules["frappe"] = saved
            else:
                sys.modules.pop("frappe", None)


class TestWiringV6(unittest.TestCase):
    def test_hooks_patches_and_doctypes(self):
        h = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertIn('"ecentric_workspace.internal_posts.schedule.publish_due"', h)
        self.assertIn('"ecentric_workspace.internal_posts.ack.remind_due"', h)
        patches = io.open(os.path.join(APP, "patches.txt"), encoding="utf-8").read()
        self.assertIn("ecentric_workspace.internal_posts.patches.p002_read_receipt_kind", patches)
        self.assertLess(patches.index("[post_model_sync]"), patches.index("p002_read_receipt_kind"),
                        "patch cot moi phai chay SAU dong bo DocType")
        post = json.load(io.open(os.path.join(APP, "internal_posts", "doctype", "ec_internal_post",
                                              "ec_internal_post.json"), encoding="utf-8"))
        names = [f["fieldname"] for f in post["fields"]]
        for f in ("publish_at", "notify_teams", "allow_comments", "require_ack", "ack_deadline", "ack_reminded_on"):
            self.assertIn(f, names)
            self.assertIn(f, post["field_order"])
        cm = json.load(io.open(os.path.join(APP, "internal_posts", "doctype", "ec_post_comment",
                                            "ec_post_comment.json"), encoding="utf-8"))
        self.assertEqual({p["role"] for p in cm["permissions"]}, {"System Manager", "HR Manager"},
                         "nhan vien khong doc / ghi thang bang binh luan")

    def test_api_has_no_user_param(self):
        import ast
        src = io.open(os.path.join(APP, "internal_posts", "api.py"), encoding="utf-8").read()
        for node in ast.parse(src).body:
            if isinstance(node, ast.FunctionDef) and any(
                    "whitelist" in ast.dump(d) for d in node.decorator_list):
                self.assertNotIn("user", [a.arg for a in node.args.args], node.name)

    def test_new_js_clean(self):
        for f in ("ec_internal_posts_aiw.js",):
            src = io.open(os.path.join(APP, "public", "js", f), encoding="utf-8").read()
            self.assertNotIn("{{", src)
            self.assertNotIn("alert(", src)
            self.assertNotIn("confirm(", src)


if __name__ == "__main__":
    unittest.main()
