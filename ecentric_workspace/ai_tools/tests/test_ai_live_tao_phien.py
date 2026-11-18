# Copyright (c) 2026, eCentric and contributors
"""18/11 - Tao phien live ngay tren /ai-live + form gon. Phien = (may, ma live): 2 may cung L1 binh thuong, cung may
thi cam; ten phien {may}-{ma live}; phien moi o Nhap (app chua nhan) toi khi Phat hanh; may khoa sau khi tao;
moi o cua phien di qua Nhap. Chay ngoai Frappe."""
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.create_session_service import CreateSessionService
from ecentric_workspace.ai_tools.features.ai_live.application.discard_draft_service import DiscardDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.list_sessions_service import ListSessionsService
from ecentric_workspace.ai_tools.features.ai_live.application.resolve_draft_service import ResolveDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.session_form_service import SessionFormService
from ecentric_workspace.ai_tools.features.ai_live.application.sync_overview_service import SyncOverviewService
from ecentric_workspace.ai_tools.features.ai_live.application.update_session_service import UpdateSessionService
from ecentric_workspace.ai_tools.features.ai_live.application.validate_session_service import ValidateSessionService
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_form_rules as F
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import FakeHealth, FakeSettings
from ecentric_workspace.ai_tools.tests.test_ai_live_schedule_publish import DAILY, World, at
from ecentric_workspace.ai_tools.tests.test_ai_live_session import FakeSessions, doc, sess, slot

EDIT, SCHED, VIEWER = ["EC AI Content"], ["AI Live Scheduler"], ["AI Live Viewer"]


class FakeKits:
    def __init__(self, names=("kit1",)):
        self.names = set(names)

    def exists(self, name):
        return name in self.names

    def list(self, brand=None, limit=100):
        return [{"name": n, "title": n.upper(), "brand": "friso"} for n in sorted(self.names)]


def form(**kw):
    d = {"machine": "MAY01", "live_id": "L1", "platform": "TikTok", "brand": "friso", "tiktok_username": "@friso.vn",
         "slots": [slot("19:00", "22:00", DAILY)]}
    d.update(kw)
    return d


class Tao(World):
    def __init__(self, t=None, sessions=()):
        super().__init__(t or at(12))
        self.ss = FakeSessions(list(sessions))
        self.kits = FakeKits()

    def create(self, roles=EDIT, **kw):
        return CreateSessionService(self.ss, self.machines, self.kits, self.clock).execute("op@ec", roles, form(**kw))

    def update(self, name, roles=EDIT, **kw):
        return UpdateSessionService(self.ss, self.machines, self.kits, self.clock).execute("op@ec", roles, name, kw)

    def field_err(self, fn, *a, **kw):
        with self.case.assertRaises(C.AiLiveError) as cm:
            fn(*a, **kw)
        return (cm.exception.data or {}).get("field"), str(cm.exception)


class TestCreate(unittest.TestCase):
    def w(self, **kw):
        w = Tao(**kw)
        w.case = self
        return w

    def test_1_create_is_draft_until_publish(self):
        """Spec 1: tao -> phien moi o Nhap, may chua nhan; Phat hanh -> may nhan, id app = ma live."""
        w = self.w()
        out = w.create()
        s = out["session"]
        self.assertEqual(s["id"], "MAY01-L1")
        self.assertEqual(s["live"], "L1")
        self.assertTrue(out["unpublished"])
        self.assertEqual(out["state"], C.DraftState.READY)
        self.assertEqual(out["diff"][0], "Phiên mới trên máy MAY01 – friso")
        self.assertEqual(s["slots"], [])                      # bang khung (ban phat hanh) con rong
        self.assertNotIn("L1", w.lives())                     # app chua nhan
        listed = ListSessionsService(w.ss, FakeHealth(), FakeSettings(), w.machines, clock=w.clock).execute(EDIT)
        row = next(r for r in (listed.get("sessions") or listed.get("rows") or []) if r["id"] == "MAY01-L1")
        self.assertTrue(row["unpublished"])
        res = w.publish()
        self.assertTrue(res["published"], res)
        self.assertEqual(w.cmds.rows["c1"]["live"], "L1")     # lenh tai lai lich mang MA LIVE
        lv = w.lives()["L1"]
        self.assertEqual(lv["title"], "friso TikTok 1")       # ten trong -> "<Brand> <San> <so>"
        self.assertEqual(lv["username"] if "username" in lv else lv.get("tiktok_username"), "friso.vn")
        self.assertFalse(P.is_new(w.ss.get("MAY01-L1")))

    def test_2_same_live_two_machines_ok_same_machine_rejected(self):
        w = self.w()
        w.create()
        w.create(machine="MAY02")                             # MAY02 giao friso
        self.assertEqual(sorted(w.ss.rows), ["MAY01-L1", "MAY02-L1"])
        field, msg = w.field_err(w.create)
        self.assertEqual(field, "live_id")
        self.assertIn("Máy MAY01 đã có phiên cho live L1", msg)
        w.publish()
        self.assertIn("L1", w.lives("MAY01"))
        self.assertIn("L1", w.lives("MAY02", "u2"))

    def test_3_shopee_drops_username(self):
        w = self.w()
        out = w.create(platform="Shopee", tiktok_username="abc")
        self.assertEqual(w.ss.get(out["session"]["id"])["draft"]["tiktok_username"], "")
        self.assertEqual(out["warning"], "")
        out = w.create(live_id="L2", tiktok_username="")
        self.assertIn("Chưa có kênh TikTok", out["warning"])  # vang, khong chan

    def test_4_manual_live_id_and_field_errors(self):
        w = self.w()
        for kw, field in ((dict(live_id=""), "live_id"), (dict(live_id="L 1"), "live_id"), (dict(live_id="a.b"), "live_id"),
                          (dict(live_id="x" * 33), "live_id"), (dict(machine=""), "machine"), (dict(machine="MAY09"), "machine"),
                          (dict(platform=""), "platform"), (dict(brand=""), "brand"), (dict(brand="wilmar", machine="MAY02"), "brand"),
                          (dict(tiktok_username="a b"), "tiktok_username"), (dict(lc_open_before_min="0"), "lc_open_before_min"),
                          (dict(lc_open_before_min="61"), "lc_open_before_min"), (dict(kit="khong_co"), "kit"),
                          (dict(slots=[slot("19:00", "21:00", DAILY), slot("20:00", "22:00", DAILY)]), "slots"),
                          (dict(watch_url="http://x"), "watch_url"), (dict(mode="turbo"), "mode")):
            self.assertEqual(w.field_err(w.create, **kw)[0], field, kw)
        self.assertEqual(w.ss.rows, {})

    def test_5_defaults(self):
        w = self.w()
        w.create(title="Friso tối", lc_open_before_min="15", kit="kit1", mode="lite", shop_name="Friso Official")
        r = w.ss.rows["MAY01-L1"]
        self.assertEqual((r["auto_obs_start"], r["enabled"], r["obs_port"]), (1, 1, 0))
        self.assertEqual(r["published_source"], C.PubSource.NEW)
        d = r["draft"]
        self.assertEqual((d["title"], d["lc_open_before_min"], d["kit"], d["mode"]), ("Friso tối", 15, "kit1", "lite"))
        w.publish()
        lv = w.lives()["L1"]
        self.assertEqual((lv["title"], lv["lc_open_before_min"]), ("Friso tối", 15))

    def test_6_edit_goes_through_draft_and_viewer_blocked(self):
        w = self.w()
        w.create()
        w.publish()
        out = w.update("MAY01-L1", title="Friso đêm", slots=[slot("20:00", "23:00", DAILY)])
        self.assertEqual(out["state"], C.DraftState.READY)
        self.assertIn("Đổi tên phiên: friso TikTok 1 → Friso đêm", out["diff"])
        self.assertEqual(w.lives()["L1"]["title"], "friso TikTok 1")          # chua phat hanh -> may chua doi
        w.publish()
        self.assertEqual(w.lives()["L1"]["title"], "Friso đêm")
        for roles in (VIEWER, ["Employee"]):
            with self.assertRaises(C.AiLivePermission):
                w.create(roles=roles, live_id="L9")
            with self.assertRaises(C.AiLivePermission):
                w.update("MAY01-L1", roles=roles, title="x")
            with self.assertRaises(C.AiLivePermission):
                SessionFormService(w.ss, w.machines, w.kits, FakeHealth(), w.clock).execute(roles)
        w.create(roles=SCHED, live_id="L3")                                    # Scheduler tao duoc

    def test_edit_unpublished_mirrors_record(self):
        """Phien chua phat hanh: sua ten -> danh sach / Dong bo hien ten moi ngay (app chua nhan nen khong lech)."""
        w = self.w()
        w.create()
        out = w.update("MAY01-L1", title="Friso tối mới", platform="Shopee")
        self.assertEqual((w.ss.rows["MAY01-L1"]["title"], w.ss.rows["MAY01-L1"]["platform"]), ("Friso tối mới", "Shopee"))
        self.assertEqual(w.ss.rows["MAY01-L1"]["tiktok_username"], "")
        self.assertTrue(out["unpublished"])
        self.assertTrue(P.is_new(w.ss.get("MAY01-L1")))
        self.assertNotIn("L1", w.lives())

    def test_machine_and_live_locked(self):
        w = self.w()
        w.create()
        self.assertEqual(w.field_err(w.update, "MAY01-L1", machine="MAY02")[0], "machine")
        self.assertEqual(w.field_err(w.update, "MAY01-L1", live_id="L2")[0], "live_id")
        w.update("MAY01-L1", machine="MAY01", live_id="L1", title="ok")         # o khoa gui lai y nguyen: bo qua

    def test_new_session_cannot_be_discarded(self):
        w = self.w(sessions=[sess("a")])
        w.create()
        w.draft("a", obs_port=4460)
        self.assertEqual(DiscardDraftService(w.ss, w.clock).execute("op", EDIT)["discarded"], ["a"])   # bo qua phien moi
        self.assertTrue(w.ss.get("MAY01-L1")["draft"])
        with self.assertRaises(C.AiLiveError):
            DiscardDraftService(w.ss, w.clock).execute("op", EDIT, '["MAY01-L1"]')
        with self.assertRaises(C.AiLiveError):
            ResolveDraftService(w.ss, w.clock).execute("op", EDIT, "MAY01-L1", 0)
        ov = SyncOverviewService(w.ss, w.machines, w.sched, w.pub(), w.clock).execute(EDIT)
        self.assertTrue(next(d for d in ov["drafts"] if d["id"] == "MAY01-L1")["new"])

    def test_enabled_toggle_applies_now(self):
        w = self.w()
        w.create(enabled=0)
        self.assertEqual(w.ss.rows["MAY01-L1"]["enabled"], 0)
        w.update("MAY01-L1", enabled=1)
        self.assertEqual(w.ss.rows["MAY01-L1"]["enabled"], 1)

    def test_form_and_live_options(self):
        w = self.w()
        w.machines.rows["MAY01"].update(hb_last_seen_ts=at(11, 58), hb_known_lives=[
            {"live": "L1", "name": "Live 1", "platform": "TikTok", "brand": "friso", "seen": at(11, 58)},
            {"live": "L2", "name": "", "platform": "", "brand": "", "seen": at(11, 58)}])
        w.create()
        svc = SessionFormService(w.ss, w.machines, w.kits, FakeHealth(), w.clock)
        f = svc.execute(EDIT)
        self.assertEqual([m["code"] for m in f["machines"]], ["MAY01", "MAY02"])
        self.assertEqual(f["machines"][0]["brands"], ["friso", "wilmar"])
        self.assertTrue(f["machines"][0]["online"])
        self.assertFalse(f["machines"][1]["online"])
        opt = svc.live_options(EDIT, "MAY01")
        l1 = opt["lives"][0]
        self.assertEqual(l1["label"], "L1 · Live 1 – TikTok (brand friso)")
        self.assertTrue(l1["taken"])
        self.assertEqual(l1["session"], "MAY01-L1")
        self.assertFalse(opt["lives"][1]["taken"])
        self.assertEqual(opt["message"], "")
        off = svc.live_options(EDIT, "MAY02")
        self.assertEqual((off["lives"], off["message"]), ([], C.SessMsg.NO_LIVES))
        edit = svc.execute(EDIT, "MAY01-L1")["session"]
        self.assertEqual((edit["live_id"], edit["machine"], edit["unpublished"]), ("L1", "MAY01", True))


class TestIdentity(unittest.TestCase):
    def test_validate_doc_unique_per_machine(self):
        ss = FakeSessions([sess("MAY01-friso_tt", live="friso_tt", obs_port=0)])
        svc = ValidateSessionService(ss, World(at(12)).machines, clock=lambda: at(12))
        with self.assertRaises(C.AiLiveError) as cm:
            svc.execute(doc(name="x", obs_port=0))
        self.assertEqual(cm.exception.data, {"field": "live_id"})
        svc.execute(doc(name="MAY02-friso_tt", machine="MAY02", obs_port=0))     # may khac: binh thuong

    def test_session_lookup_and_slot_report_join(self):
        ss = [sess("MAY01-L1", live="L1"), sess("MAY02-L1", live="L1", machine="MAY02")]
        look = S.session_lookup(S.index(ss))
        self.assertEqual((look("MAY01", "L1"), look("MAY02", "L1"), look("MAY03", "L1")), ("MAY01-L1", "MAY02-L1", None))
        # bao cao khung gio: L1 cua MAY01 la live ERP; L1 tren MAY02 (khong co phien) -> ngoai ke hoach
        from ecentric_workspace.ai_tools.tests.test_ai_live_wallboard import T10, World as Wall, rec
        w = Wall(T10, [sess("MAY01-L1", live="L1", slots=[slot("10:00", "12:00", DAILY)])])
        w.machines.rows["MAY02"] = {"machine_code": "MAY02", "label": "Máy 2", "enabled": 1, "user": "u2", "brands": "friso"}
        w.report([rec(live="L1")])
        w.report([rec(live="L1")], user="u2", machine="MAY02")
        rows = {(r["machine"], r["live"]): r["off_plan"] for r in w.reports.rows.values()}
        self.assertEqual(rows, {("MAY01", "L1"): 0, ("MAY02", "L1"): 1})
        new = Wall(T10, [dict(sess("MAY01-L1", live="L1"), published_source=C.PubSource.NEW)])
        new.report([rec(live="L1")])                                       # phien chua phat hanh -> chua tinh ERP
        self.assertEqual(list(new.reports.rows.values())[0]["off_plan"], 1)

    def test_known_lives_merge(self):
        prev = [{"live": "L1", "name": "Live 1", "platform": "TikTok", "brand": "friso", "seen": 100.0},
                {"live": "OLD", "name": "", "platform": "", "brand": "", "seen": 1.0}]
        now = 100.0 + C.KNOWN_LIVE_KEEP_S
        out = W.known_lives(prev, [{"live": "L2", "brand": "friso", "platform": "shopee", "name": "Live 2"},
                                   {"live": "L1", "brand": "friso"}, {"live": "bad id"}], now)
        self.assertEqual([x["live"] for x in out], ["L1", "L2"])                 # OLD qua 30 ngay -> bo
        self.assertEqual(out[0]["name"], "Live 1")                              # nhip moi khong co ten -> giu ten cu
        self.assertEqual(out[1]["platform"], "Shopee")
        self.assertEqual(F.live_label(out[1]), "L2 · Live 2 – Shopee (brand friso)")
        self.assertEqual(F.live_label({"live": "L3"}), "L3")

    def test_heartbeat_stores_known_lives(self):
        from ecentric_workspace.ai_tools.tests.test_ai_live_machine_watch import T0, World as Watch
        from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import live
        w = Watch(T0)
        w.machines.get = lambda code: w.machines.rows.get(code)
        w.push([live(live="L1", name="Live 1", platform="TikTok"), live(live="L2", state="idle")])
        w.push([live(live="L1")], minimal=True)                            # nhip rut gon: khong mat L2
        self.assertEqual([(x["live"], x["name"]) for x in w.machines.rows["MAY01"]["hb_known_lives"]],
                         [("L1", "Live 1"), ("L2", "")])


if __name__ == "__main__":
    unittest.main()
