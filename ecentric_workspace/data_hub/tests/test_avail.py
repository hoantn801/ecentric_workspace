# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu DOT 2 - Data availability, de xuat data can crawl, ke hoach DA-, do tuoi, Thu vien bao
cao, goi y tuong tu. Chay THAT avail_domain / avail_service (+ service / ops_service / pm_sync dot 1) tren
repo gia + PM gia, render /du-lieu/san-co bang jinja2.

    python -m unittest ecentric_workspace.data_hub.tests.test_avail

Fixture jsdom dot 2 (tests/js/fixtures/avail_*.html + avail_api.json) render tu bo mau nay; sinh lai:
    EDH_UPDATE_FIXTURES=1 python -m unittest ecentric_workspace.data_hub.tests.test_avail
"""
import ast
import datetime as dt
import io
import json
import os
import re
import types
import unittest

from ecentric_workspace.data_hub.tests import fake as F  # noqa: E402  (dat frappe gia neu thieu)
from ecentric_workspace.data_hub.tests import fake_avail as FA
from ecentric_workspace.data_hub.tests import test_data_hub as T
from ecentric_workspace.data_hub import avail_domain as A
from ecentric_workspace.data_hub import avail_service as AS
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D
from ecentric_workspace.data_hub import notify as N
from ecentric_workspace.data_hub import ops_service as O
from ecentric_workspace.data_hub import pm_sync as P
from ecentric_workspace.data_hub import service as S
from ecentric_workspace.data_hub.patches import p002_seed_data_availability as P2

d = dt.date
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "js", "fixtures")
APP = T.APP


def fresh(seed=True):
    r = F.FakeRepo()
    pm = F.FakePM(r)
    if seed:
        FA.seed(r)
    return r, pm


def row(r, team, dtype, plat):
    return r.avail_find(team, dtype, plat)


def prop(**kw):
    x = {"department": "Commercial - EC", "data_type": "Video", "platforms": ["Shopee"], "purpose": "Đo hiệu quả video",
         "urgency": C.PRI_NORMAL, "frequency": C.FREQ_DAILY}
    x.update(kw)
    return x


def plan(**kw):
    x = {"team": "Commercial", "data_type": "Video", "platforms": ["Shopee", "TikTok"], "channels": ["sharepoint", "dw"],
         "assignee": F.LINH, "method": "Crawl"}
    x.update(kw)
    return x


# ====================================================================== domain =========
class TestDomain(unittest.TestCase):
    def test_platform_names(self):
        self.assertEqual([A.norm_platform(x) for x in ("tiktok", " Tiktok ", "SHOPEE", "Misa")],
                         ["TikTok", "TikTok", "Shopee", "Misa"])
        self.assertEqual(A.column_of("Oms Boxme"), C.OTHER_PLATFORM)
        self.assertEqual(A.parse_platforms(["Shopee", "tiktok", "Khác", "", 3], "Misa, shopee; GOV"),
                         ["Shopee", "TikTok", "Misa", "GOV"])

    def test_seed_52_rows_and_coverage_matches_excel(self):
        rows = P2.rows()
        self.assertEqual(len(rows), 52)
        self.assertEqual(len({(r["team"], r["data_type"], r["platform"]) for r in rows}), 52, "khong trung")
        self.assertNotIn("Tiktok", {r["platform"] for r in rows}, "ten san chuan hoa")
        cov = A.coverage(rows)
        self.assertEqual((cov["sharepoint"], cov["dw"], cov["powerbi"]), (73, 73, 40), "= mockup")
        self.assertEqual(cov["empty"], 14)
        self.assertEqual(sum(r["front_priority"] for r in rows), 3)

    def test_matrix_groups_columns_and_other(self):
        r, _ = fresh()
        teams = A.matrix(r.avail_rows(), {}, r.now())
        self.assertEqual([t["team"] for t in teams], ["Commercial", "Service", "Media", "Finance Data", "Boxme Data"])
        com = {g["data_type"]: g for g in teams[0]["groups"]}
        self.assertEqual(len(teams[0]["groups"]), 12)
        self.assertEqual(com["Product"]["cells"]["TikTok"]["state"], "data")
        self.assertTrue(com["Product"]["full"])
        self.assertEqual(com["Video"]["cells"]["Lazada"]["state"], "none")
        self.assertEqual(com["Shipping fee"]["cells"]["Shopee"], None, "khong co dong -> —")
        self.assertEqual([c["platform"] for c in com["Boxme Purchase Order"]["others"]], ["Boxme"])
        boxme = {g["data_type"]: g for g in teams[4]["groups"]}
        self.assertEqual([c["platform"] for c in boxme["Orderline"]["others"]], ["Omisell", "Oms Boxme"],
                         "Khac nhieu san trong mot nhom (mockup de mat san thu hai)")
        self.assertTrue(boxme["Orderline"]["front"])
        self.assertTrue(com["Finance"]["gap"] is False and com["Finance"]["full"] is False, "thieu Power BI khong phai 'chua co'")
        self.assertEqual(com["Finance"]["cells"]["Shopee"]["dots"], {"sharepoint": True, "dw": True, "powerbi": False})

    def test_gaps_only_missing_data_with_sources(self):
        r, _ = fresh()
        teams = A.matrix(r.avail_rows(), {}, r.now())
        props = [{"name": "DP-1", "status": C.PROP_PENDING, "team": "Service", "data_type": "Affiliate creator orders",
                  "platforms": '["TikTok"]'},
                 {"name": "DP-2", "status": C.PROP_PENDING, "team": "Media", "data_type": "Meta Ads",
                  "platforms": '["Facebook"]'},
                 {"name": "DP-3", "status": C.PROP_APPROVED, "team": "Commercial", "data_type": "Video",
                  "platforms": '["Shopee"]', "urgency": C.PRI_HIGH, "resulting_ticket": None},
                 {"name": "DP-4", "status": C.PROP_REJECTED, "team": "Commercial", "data_type": "Live", "platforms": "[]"}]
        g = {x["data_type"]: x for x in A.gaps(teams, props)}
        self.assertNotIn("Finance", g, "chi thieu Power BI -> khong vao Can bo sung")
        self.assertEqual(g["Video"]["platforms"], ["Shopee", "TikTok", "Lazada"])
        self.assertEqual(g["Video"]["channels"], "SharePoint · DW · Power BI")
        self.assertEqual((g["Video"]["source"], g["Video"]["proposal"], g["Video"]["urgency"]), ("approved", "DP-3", C.PRI_HIGH))
        self.assertEqual(g["Affiliate creator orders"]["source"], "pending")
        self.assertEqual(g["Affiliate creator orders"]["proposal"], "", "de xuat chua duyet khong gan vao ke hoach")
        self.assertTrue(g["Meta Ads"]["only_proposal"])
        self.assertEqual(g["Meta Ads"]["platforms"], ["Facebook"])
        self.assertEqual(g["Live"]["source"], "table", "de xuat bi tu choi khong doi nguon")
        self.assertEqual(len(g), 10)

    def test_freshness(self):
        now = dt.datetime(2026, 11, 9, 9, 30)
        base = {"in_sharepoint": 1}
        f = lambda **kw: A.freshness(dict(base, **kw), now)["state"]
        self.assertEqual(f(frequency=C.FREQ_DAILY, last_updated=now - dt.timedelta(hours=47)), "ok")
        self.assertEqual(f(frequency=C.FREQ_DAILY, last_updated=now - dt.timedelta(hours=49)), "stale")
        self.assertEqual(f(frequency=C.FREQ_HOURLY, last_updated=now - dt.timedelta(hours=25)), "stale")
        self.assertEqual(f(frequency=C.FREQ_WEEKLY, last_updated=now - dt.timedelta(days=7)), "ok")
        self.assertEqual(f(frequency=C.FREQ_MONTHLY, last_updated=now - dt.timedelta(days=36)), "stale")
        self.assertEqual(f(frequency=C.FREQ_NONE, last_updated=now - dt.timedelta(days=400)), "ok", "khong dinh ky")
        self.assertEqual(f(frequency=C.FREQ_DAILY), "unknown")
        self.assertEqual(A.freshness({"frequency": C.FREQ_DAILY, "last_updated": now - dt.timedelta(days=9)}, now)["state"], "",
                         "o chua co du lieu khong xet do tuoi")

    def test_proposal_due_and_countdown(self):
        rules = D.rules_view(None)
        self.assertEqual(A.proposal_due(dt.datetime(2026, 11, 6, 15, 20), rules), dt.datetime(2026, 11, 9, 15, 20), "T6 -> T2")
        self.assertEqual(A.proposal_due(dt.datetime(2026, 11, 19, 10), rules, F.HOLIDAYS), dt.datetime(2026, 11, 23, 10),
                         "bo ngay le 20/11")
        now = dt.datetime(2026, 11, 9, 9, 30)
        self.assertEqual(A.countdown(dt.datetime(2026, 11, 9, 13, 20), now), ("còn 4h", False))
        self.assertEqual(A.countdown(dt.datetime(2026, 11, 10, 9, 5), now), ("còn 24h", False))
        self.assertEqual(A.countdown(dt.datetime(2026, 11, 12, 9, 30), now), ("còn 3 ngày", False))
        self.assertEqual(A.countdown(dt.datetime(2026, 11, 9, 6, 30), now), ("quá hạn 3h", True))

    def test_proposal_detail_fields(self):
        depts = {"Commercial - EC": "Commercial", "Service - EC": "Service"}
        now = dt.datetime(2026, 11, 9, 9, 30)
        ok = A.normalize_proposal(prop(source_links="https://a.vn/x\n https://b.vn/y , https://a.vn/x",
                                       scope="12 brand", data_from="2026-10-01", data_to="2026-10-31",
                                       channels=["powerbi", "xx", "dw"], needed_by="2026-12-01T17:00",
                                       urgency=C.PRI_HIGH, urgency_reason="Chốt ngân sách"), 0, depts, now)
        self.assertEqual((ok["department"], ok["team"]), ("Commercial - EC", "Commercial"), "team = department_name")
        self.assertEqual(ok["source_links"], ["https://a.vn/x", "https://b.vn/y"], "link: tach dong, bo trung")
        self.assertEqual(ok["channels"], ["dw", "powerbi"], "kenh: chi khoa hop le, theo thu tu chuan")
        self.assertEqual((D.iso(ok["data_from"]), D.iso(ok["data_to"])), ("2026-10-01", "2026-10-31"))
        self.assertEqual(ok["needed_by"], dt.datetime(2026, 12, 1, 17, 0))
        self.assertEqual(ok["urgency_reason"], "Chốt ngân sách")
        self.assertEqual(A.normalize_proposal(prop(urgency_reason="bo qua"), 0, depts, now)["urgency_reason"], "",
                         "muc Binh thuong khong luu ly do")
        bad = (
            (dict(department=""), "Chọn phòng ban"),
            (dict(department="Ma - EC"), "không có trong ERP"),
            (dict(frequency=""), "tần suất"),
            (dict(frequency="Mỗi phút"), "Tần suất không hợp lệ"),
            (dict(urgency=C.PRI_HIGH), "cần ghi lý do"),
            (dict(urgency=C.PRI_URGENT, urgency_reason="  "), "cần ghi lý do"),
            (dict(source_links="shopee.vn/abc"), "http://"),
            (dict(source_links="javascript:alert(1)"), "http://"),
            (dict(source_links="\n".join("https://x.vn/%d" % i for i in range(C.SOURCE_LINKS_MAX + 1))), "Tối đa"),
            (dict(data_from="2026-10-31", data_to="2026-10-01"), "không được trước"),
            (dict(data_from="31/10/2026"), "ngày không hợp lệ"),
            (dict(needed_by="2026-11-09T09:00"), "tương lai"),
            (dict(needed_by="mai"), "không hợp lệ"),
            (dict(scope="x" * (C.SCOPE_MAX + 1)), "Phạm vi dài"),
        )
        for kw, msg in bad:
            with self.assertRaises(D.Invalid, msg=str(kw)) as cm:
                A.normalize_proposal(prop(**kw), 0, depts, now)
            self.assertIn(msg, " ".join(cm.exception.errors), kw)
        brief = A.proposal_brief({"frequency": "Hằng ngày", "scope": "12 brand", "range_text": "01/10/2026 – nay",
                                  "links": ["a", "b"], "files": [1], "needed_by_fmt": "17:00 01/12/2026"})
        self.assertEqual(brief, "Tần suất: Hằng ngày · Phạm vi: 12 brand · Dữ liệu 01/10/2026 – nay · 2 link nguồn · "
                                "1 tệp hướng dẫn · cần trước 17:00 01/12/2026")

    def test_validation(self):
        with self.assertRaises(D.Invalid) as cm:
            A.normalize_proposal({"platforms": [], "urgency": "?"})
        e = " ".join(cm.exception.errors)
        for s in ("Chọn phòng ban", "loại dữ liệu", "ít nhất một sàn", "tần suất", "dùng để làm gì", "Mức cần gấp"):
            self.assertIn(s, e)
        with self.assertRaises(D.Invalid):
            A.normalize_proposal(prop(), sent_today=C.PROPOSAL_DAILY_LIMIT)
        self.assertEqual(A.normalize_proposal(prop(platforms=[], other_platform="Misa"))["platforms"], ["Misa"])
        with self.assertRaises(D.Invalid) as cm:
            A.normalize_plan({"team": "x", "data_type": "y", "platforms": ["Shopee"], "channels": [], "method": "?"})
        self.assertIn("kênh đích", " ".join(cm.exception.errors))
        with self.assertRaises(D.Invalid):
            A.normalize_library({"title": "x", "link": "javascript:alert(1)"})
        with self.assertRaises(D.Invalid):
            A.normalize_row({"team": "A", "data_type": "B", "platform": "Khác"})
        with self.assertRaises(D.Invalid):
            A.normalize_row({"team": "A", "data_type": "B", "platform": "X", "frequency": "Mỗi phút"})
        v = A.normalize_row({"team": "A", "data_type": "B", "platform": "tiktok", "in_dw": "1", "last_updated": "2026-11-09T08:15"})
        self.assertEqual((v["platform"], v["in_dw"], v["in_sharepoint"], v["last_updated"]),
                         ("TikTok", 1, 0, dt.datetime(2026, 11, 9, 8, 15)))

    def test_similar_vietnamese_tokens(self):
        self.assertEqual(A.fold("Báo cáo Đơn hàng Lazada"), "bao cao don hang lazada")
        self.assertEqual(A.tokens("Dashboard PnL theo ngày cho brand Friso"), ["pnl", "friso"], "bo tu chung")
        lib = [{"t": "Dashboard PnL tổng hợp"}, {"t": "Báo cáo tồn kho Boxme"}, {"t": "Affiliate TikTok creator"}]
        hit = [x["t"] for _, x in A.similar("PnL theo ngày Friso", lib, lambda x: x["t"])]
        self.assertEqual(hit, ["Dashboard PnL tổng hợp"])
        self.assertEqual(A.similar("Dashboard báo cáo", lib, lambda x: x["t"]), [], "chi tu chung -> khong goi y")
        self.assertEqual([x["t"] for _, x in A.similar("tồn kho", lib, lambda x: x["t"])], ["Báo cáo tồn kho Boxme"],
                         "co dau / khong dau van khop")
        self.assertEqual(A.similar("affiliate", lib, lambda x: x["t"])[0][1]["t"], "Affiliate TikTok creator")
        many = [{"t": "Video Shopee TikTok"}]
        self.assertEqual(A.similar("Video Lazada Shopee doanh thu", many, lambda x: x["t"])[0][1]["t"], "Video Shopee TikTok",
                         ">= 2 tu chung")
        self.assertEqual(A.similar("Video Lazada doanh thu ngành", many, lambda x: x["t"]), [], "1 tu / cau dai -> khong")


# ====================================================================== seed patch =======
class _FakeFrappeDB(object):
    def __init__(self, store, fail_on=None):
        self.store, self.fail_on = store, fail_on

    def exists(self, dt_, name=None):
        return dt_ == "DocType"


class TestSeedPatch(unittest.TestCase):
    def run_patch(self, store, fail_on=None, no_doctype=False):
        errors = []

        class Doc(object):
            def __init__(self, v):
                self.v = v

            def insert(self, ignore_permissions=False):
                if fail_on and self.v.get("data_type") == fail_on:
                    raise RuntimeError("boom")
                store.append(self.v)

        fr = types.SimpleNamespace(
            db=types.SimpleNamespace(exists=lambda dt_, *a: (not no_doctype) and dt_ == "DocType"),
            get_all=lambda dt_, fields=None, limit_page_length=0: [types.SimpleNamespace(**{k: x[k] for k in fields}) and
                                                                    {k: x[k] for k in fields} for x in store],
            get_doc=lambda v: Doc(v), log_error=lambda title=None, message=None: errors.append(title),
            get_traceback=lambda: "tb")
        saved = P2.frappe
        P2.frappe = fr
        try:
            P2.execute()
        finally:
            P2.frappe = saved
        return errors

    def test_idempotent_never_overwrites_never_raises(self):
        store = [{"team": "Commercial", "data_type": "Product", "platform": "TikTok", "in_sharepoint": 0, "in_dw": 0,
                  "in_powerbi": 0, "doctype": C.AVAIL_DT}]
        self.assertEqual(self.run_patch(store), [])
        self.assertEqual(len(store), 52, "dong da co (Tiktok ~ TikTok) giu nguyen, khong tao trung")
        self.assertEqual(store[0]["in_sharepoint"], 0, "khong ghi de dong team Data da sua")
        self.run_patch(store)
        self.assertEqual(len(store), 52, "chay lai khong tao them")
        store2 = []
        errs = self.run_patch(store2, fail_on="Video")
        self.assertEqual(len(store2), 49)
        self.assertEqual(len(errs), 3, "dong loi -> Error Log, cac dong khac van vao")
        store3 = []
        self.assertEqual(self.run_patch(store3, no_doctype=True), [])
        self.assertEqual(store3, [], "DocType chua co -> bo qua")


# ====================================================================== de xuat ==========
class TestProposals(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = fresh()

    def test_create_due_one_working_day_and_notify_team(self):
        self.r.at(d(2026, 11, 6), 15, 20)       # thu Sau
        out = AS.create_proposal(F.THU, prop(platforms=["shopee", "TikTok"]), repo=self.r)
        p = self.r.proposal_get(out["name"])
        self.assertEqual((p["status"], p["proposer"], p["due_at"]), (C.PROP_PENDING, F.THU, dt.datetime(2026, 11, 9, 15, 20)))
        self.assertEqual(json.loads(p["platforms"]), ["Shopee", "TikTok"])
        self.assertEqual(p["rule_version"], "SLA-v1")
        sent = self.r.sent(C.EV_PROPOSAL)
        self.assertEqual(sorted(n["to"] for n in sent), sorted([F.LINH, F.HOAN, F.DUNG]))
        self.assertEqual(sent[0]["url"], C.ROUTE_AVAIL)
        with self.assertRaises(S.DataHubError):
            AS.create_proposal(F.THU, prop(purpose=""), repo=self.r)

    def test_create_stores_detail_and_files(self):
        out = AS.create_proposal(F.THU, prop(department="Commercial - EC", frequency=C.FREQ_WEEKLY, urgency=C.PRI_URGENT,
                                             urgency_reason="Sự kiện 12.12", needed_by="2026-11-20T17:00",
                                             source_links="https://shopee.vn/a", channels=["powerbi"]),
                                 files=[{"name": "buoc-1.png", "content": b"PNG", "size": 3}], repo=self.r)
        p = self.r.proposal_get(out["name"])
        self.assertEqual((p["department"], p["team"], p["frequency"], p["urgency_reason"]),
                         ("Commercial - EC", "Commercial", C.FREQ_WEEKLY, "Sự kiện 12.12"))
        self.assertEqual((json.loads(p["source_links"]), json.loads(p["channels"])), (["https://shopee.vn/a"], ["powerbi"]))
        self.assertEqual(p["needed_by"], dt.datetime(2026, 11, 20, 17, 0))
        self.assertEqual([f["file_name"] for f in self.r.proposal_files([out["name"]])[out["name"]]], ["buoc-1.png"])
        msg = self.r.sent(C.EV_PROPOSAL)[0]["message"]
        for bit in (C.FREQ_WEEKLY, "Khẩn (Sự kiện 12.12)", "cần trước 17:00 20/11/2026"):
            self.assertIn(bit, msg)

    def test_create_rejects_bad_dept_and_files(self):
        with self.assertRaises(S.DataHubError) as cm:
            AS.create_proposal(F.THU, prop(department="Không có - EC"), repo=self.r)
        self.assertIn("không có trong ERP", str(cm.exception))
        for files, msg in (([{"name": "x.exe", "content": b"x", "size": 1}], "Không nhận loại tệp"),
                           ([{"name": "a%d.png" % i, "content": b"x", "size": 1} for i in range(C.MAX_FILES + 1)], "Tối đa"),
                           ([{"name": "big.png", "content": b"x", "size": C.FILE_MAX_BYTES + 1}], "Tệp quá")):
            with self.assertRaises(S.DataHubError) as cm:
                AS.create_proposal(F.THU, prop(), files=files, repo=self.r)
            self.assertIn(msg, str(cm.exception))
        self.assertEqual(self.r.proposal_rows(), [], "loi tep -> khong tao de xuat")

    def test_download_permission(self):
        name = AS.create_proposal(F.THU, prop(), files=[{"name": "b.png", "content": b"PNG", "size": 3}], repo=self.r)["name"]
        row = self.r.proposal_files([name])[name][0]["name"]
        for u in (F.THU, F.LINH, F.ADMIN):
            self.assertEqual(AS.download_proposal_file(u, name, row, repo=self.r), ("b.png", b"PNG"), u)
        with self.assertRaises(S.Forbidden):
            AS.download_proposal_file(F.HIEN, name, row, repo=self.r)
        with self.assertRaises(S.Forbidden):
            AS.download_proposal_file(F.OUTSIDER, name, row, repo=self.r)
        with self.assertRaises(S.NotFound):
            AS.download_proposal_file(F.THU, name, "PF-999", repo=self.r)
        other = AS.create_proposal(F.DUYEN, prop(), repo=self.r)["name"]
        with self.assertRaises(S.NotFound):
            AS.download_proposal_file(F.DUYEN, other, row, repo=self.r)   # dong tep cua de xuat khac
        # trang: link tai chi co voi nguoi duoc tai
        def files_of(user):
            v = AS.view_data(self.r, user)
            return next(p for p in v["proposals"] if p["name"] == name)["files"]
        self.assertTrue(files_of(F.LINH)[0]["url"].startswith("/api/method/ecentric_workspace.data_hub.api.download_proposal_file?"))
        self.assertTrue(files_of(F.THU)[0]["url"])
        self.assertEqual(files_of(F.HIEN)[0]["url"], "", "nguoi khac thay ten tep, khong co link tai")

    def test_team_member_proposal_not_self_notified(self):
        AS.create_proposal(F.LINH, prop(), repo=self.r)
        self.assertNotIn(F.LINH, [n["to"] for n in self.r.sent(C.EV_PROPOSAL)])

    def test_approve_creates_missing_rows_and_notifies(self):
        name = AS.create_proposal(F.THU, prop(data_type="Video", platforms=["Shopee", "Facebook"]), repo=self.r)["name"]
        before = len(self.r.avail_rows())
        out = AS.review_proposal(F.LINH, name, C.PROP_APPROVED, repo=self.r)
        self.assertEqual(out, {"status": C.PROP_APPROVED, "created": ["Facebook"]}, "Shopee da co dong -> chi tao Facebook")
        self.assertEqual(len(self.r.avail_rows()), before + 1)
        fb = row(self.r, "Commercial", "Video", "Facebook")
        self.assertFalse(A.has_data(fb))
        p = self.r.proposal_get(name)
        self.assertEqual((p["decided_by"], p["status"]), (F.LINH, C.PROP_APPROVED))
        self.assertEqual([n["to"] for n in self.r.sent(C.EV_UPDATE)], [F.THU])
        with self.assertRaises(S.DataHubError):
            AS.review_proposal(F.HOAN, name, C.PROP_REJECTED, "x", repo=self.r)    # da xu ly
        self.assertIn(("proposal", name), self.r.locks, "khoa dong truoc khi duyet")

    def test_approve_new_data_type_appears_in_gaps(self):
        name = AS.create_proposal(F.HIEN, prop(team="Media", data_type="Meta Ads", platforms=[], other_platform="Facebook"),
                                  repo=self.r)["name"]
        AS.review_proposal(F.HOAN, name, C.PROP_APPROVED, repo=self.r)
        g = {x["data_type"]: x for x in AS.view_data(self.r, F.THU)["gaps"]}["Meta Ads"]
        self.assertEqual((g["source"], g["proposal"], g["platforms"]), ("approved", name, ["Facebook"]))

    def test_reject_needs_reason(self):
        name = AS.create_proposal(F.THU, prop(), repo=self.r)["name"]
        with self.assertRaises(S.DataHubError):
            AS.review_proposal(F.LINH, name, C.PROP_REJECTED, "  ", repo=self.r)
        AS.review_proposal(F.LINH, name, C.PROP_REJECTED, "Đã có trong Kalodata", repo=self.r)
        p = self.r.proposal_get(name)
        self.assertEqual((p["status"], p["reason"]), (C.PROP_REJECTED, "Đã có trong Kalodata"))
        self.assertIn("Đã có trong Kalodata", self.r.sent(C.EV_UPDATE)[-1]["message"])
        with self.assertRaises(S.DataHubError):
            AS.review_proposal(F.LINH, "DP-9999", C.PROP_APPROVED, repo=self.r)
        with self.assertRaises(S.DataHubError):
            AS.review_proposal(F.LINH, AS.create_proposal(F.THU, prop(), repo=self.r)["name"], "Có lẽ", repo=self.r)

    def test_daily_limit(self):
        for _ in range(C.PROPOSAL_DAILY_LIMIT):
            AS.create_proposal(F.THU, prop(), repo=self.r)
        with self.assertRaises(S.DataHubError):
            AS.create_proposal(F.THU, prop(), repo=self.r)

    def test_overdue_reminder_job(self):
        self.r.at(d(2026, 11, 6), 15, 20)
        name = AS.create_proposal(F.THU, prop(), repo=self.r)["name"]
        self.r.at(d(2026, 11, 9), 9)               # con han (15:20)
        self.assertEqual(AS.run_daily(self.r)["proposal_overdue"], 0)
        self.r.at(d(2026, 11, 10), 9)
        self.assertEqual(AS.run_daily(self.r)["proposal_overdue"], 1)
        late = [n for n in self.r.sent(C.EV_OVERDUE)]
        self.assertEqual(sorted(n["to"] for n in late), sorted([F.LINH, F.HOAN, F.DUNG]))
        self.assertIn("quá hạn", late[0]["title"])
        self.assertTrue(all("2026-11-10" in n["key"] and name in n["key"] for n in late), "dedupe theo ngay")
        self.r.at(d(2026, 11, 14), 9)              # thu Bay
        self.assertEqual(AS.run_daily(self.r)["proposal_overdue"], 0)
        AS.review_proposal(F.LINH, name, C.PROP_APPROVED, repo=self.r)
        self.r.at(d(2026, 11, 16), 9)
        self.assertEqual(AS.run_daily(self.r)["proposal_overdue"], 0, "da duyet -> thoi nhac")


# ====================================================================== ke hoach DA ======
class TestPlan(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = fresh()

    def test_plan_creates_da_via_accept_flow(self):
        out = AS.plan(F.LINH, plan(start_date="2026-11-10", note="Crawl 2 sàn trước"), repo=self.r, pm=self.pm)
        code = out["code"]
        self.assertTrue(code.startswith("DA-2026-"))
        t = self.r.get(code)
        self.assertEqual((t["kind"], t["status"], t["assignee"], t["requester"]), (C.KIND_AVAILABILITY, C.ST_DOING, F.LINH, F.LINH))
        self.assertEqual((D.iso(t["start_date"]), D.iso(t["due_date"]), t["sla_days"]), ("2026-11-10", "2026-11-19", 7),
                         "ket thuc mac dinh = quy tac Crawl data moi 7 ngay lam viec")
        self.assertEqual(json.loads(t["channels"]), ["sharepoint", "dw"])
        self.assertEqual(json.loads(t["platforms"]), ["Shopee", "TikTok"])
        self.assertEqual(t["title"], "Video (Commercial) · Shopee/TikTok")
        self.assertEqual(t["pm_task"], out["pm_task"])
        self.assertEqual(self.pm.calls[0][0], "create")
        self.assertEqual(self.r.events(code), [C.EV_CREATED, C.EV_ACCEPTED, C.EV_PM])
        for p in ("Shopee", "TikTok"):
            self.assertEqual(row(self.r, "Commercial", "Video", p)["planned_ticket"], code)
        self.assertIsNone(row(self.r, "Commercial", "Video", "Lazada")["planned_ticket"])
        self.assertEqual([n for n in self.r.notes if n["code"] == code and n["event"] == C.EV_NEW], [],
                         "ke hoach khong bao 'yeu cau moi' cho team")
        g = S.gantt_data(F.THU, repo=self.r)
        bar = [b for ln in g["lanes"] for b in ln["bars"] if b["code"] == code][0]
        self.assertEqual((bar["kind"], bar["css"]), (C.KIND_AVAILABILITY, "da"))
        lane = [ln for ln in g["lanes"] if ln["key"] == F.LINH][0]
        self.assertEqual(lane["sub"], "0 yêu cầu + 1 bổ sung data")
        cells = {g_["data_type"]: g_ for g_ in AS.view_data(self.r, F.THU)["teams"][0]["groups"]}["Video"]["cells"]
        self.assertEqual((cells["Shopee"]["state"], cells["Shopee"]["plan"]["due"]), ("plan", "19/11"))
        self.assertEqual(cells["Lazada"]["state"], "none")
        self.assertNotIn(code, [x["code"] for x in S.list_rows(F.THU, repo=self.r)], "DA khong vao bang yeu cau")
        self.assertEqual(D.kpis(self.r.list_rows(), self.r.today())["doing"], 0, "KPI chi tinh yeu cau")

    def test_plan_custom_due_and_proposal_priority(self):
        name = AS.create_proposal(F.THU, prop(urgency=C.PRI_URGENT, urgency_reason="Sự kiện 11.11", platforms=["Lazada"]), repo=self.r)["name"]
        AS.review_proposal(F.HOAN, name, C.PROP_APPROVED, repo=self.r)
        out = AS.plan(F.HOAN, plan(platforms=["Lazada"], assignee=F.DUNG, proposal=name, start_date="2026-11-09"),
                      repo=self.r, pm=self.pm)
        t = self.r.get(out["code"])
        self.assertEqual((t["priority"], t["sla_days"], D.iso(t["due_date"])), (C.PRI_URGENT, 4, "2026-11-13"),
                         "muc gap cua de xuat -> he so Khan 7 x 0.5 = 4")
        self.assertEqual(t["requester"], F.THU, "DA tu de xuat: nguoi gui = nguoi de xuat (nghiem thu)")
        self.assertEqual(self.r.proposal_get(name)["resulting_ticket"], out["code"])
        self.assertIn(F.THU, [n["to"] for n in self.r.sent(C.EV_UPDATE, out["code"])], "nguoi de xuat nhan 'Team Data da nhan'")
        out2 = AS.plan(F.HOAN, plan(data_type="Live", platforms=["Lazada"], due_date="2026-11-30", start_date="2026-11-10"),
                       repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(out2["code"])["due_date"], d(2026, 11, 30), "ket thuc tu chon")
        with self.assertRaises(S.DataHubError):
            AS.plan(F.HOAN, plan(platforms=["Shopee"], proposal=name), repo=self.r, pm=self.pm)  # de xuat da co ke hoach

    def test_plan_guards(self):
        AS.plan(F.LINH, plan(), repo=self.r, pm=self.pm)
        cases = [
            (plan(platforms=["TikTok", "Lazada"]), "Đã có kế hoạch đang làm"),
            (plan(data_type="Product", platforms=["Shopee"]), "đều đã có"),
            (plan(data_type="Live", platforms=["Lazada"], assignee=F.THU), "thuộc team Data"),
            (plan(data_type="Live", platforms=["Lazada"], start_date="2026-11-06"), "trước hôm nay"),
            (plan(data_type="Live", platforms=["Lazada"], start_date="2026-11-10", due_date="2026-11-09"), "trước ngày bắt đầu"),
            (plan(data_type="Live", platforms=["Lazada"], priority="Siêu gấp"), "ưu tiên"),
            (plan(data_type="Live", platforms=["Lazada"], proposal="DP-0000-0001"), "chưa được duyệt"),
        ]
        n = len(self.r.tickets)
        for data, msg in cases:
            with self.assertRaises(S.DataHubError) as cm:
                AS.plan(F.LINH, data, repo=self.r, pm=self.pm)
            self.assertIn(msg, str(cm.exception), data)
        self.assertEqual(len(self.r.tickets), n, "loi kiem tra -> khong tao ticket mo coi")
        self.assertTrue(any(lk[0] == "avail" for lk in self.r.locks if isinstance(lk, tuple)), "khoa dong truoc khi gan")
        out = AS.plan(F.LINH, plan(data_type="Finance", platforms=["Shopee"], channels=["powerbi", "dw"]), repo=self.r, pm=self.pm)
        self.assertTrue(out["code"], "dong da co SP+DW, them Power BI van len ke hoach duoc")

    def test_plan_new_platform_creates_row(self):
        out = AS.plan(F.LINH, plan(data_type="Video", platforms=[], other_platform="Facebook"), repo=self.r, pm=self.pm)
        fb = row(self.r, "Commercial", "Video", "Facebook")
        self.assertEqual(fb["planned_ticket"], out["code"])


class TestDaCompletion(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = fresh()

    def test_team_plan_done_closes_and_flips_cells(self):
        code = AS.plan(F.LINH, plan(channels=["sharepoint", "dw"]), repo=self.r, pm=self.pm)["code"]
        self.r.at(d(2026, 11, 13), 16)
        out = O.mark_done(F.LINH, code, note="Đã đổ 2 sàn", repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((out["status"], t["status"], t["acceptance"]), (C.ST_DONE, C.ST_DONE, ""),
                         "DA team Data tu len -> Hoan tat luon, khong cho nghiem thu")
        self.assertEqual(t["closed_at"], self.r.now())
        for p in ("Shopee", "TikTok"):
            x = row(self.r, "Commercial", "Video", p)
            self.assertEqual((x["in_sharepoint"], x["in_dw"], x["in_powerbi"]), (1, 1, 0), "chi bat kenh da chon")
            self.assertEqual(x["last_updated"], self.r.now())
            self.assertEqual(x["data_owner"], F.LINH, "nguoi xu ly thanh nguoi phu trach")
        self.assertEqual(row(self.r, "Commercial", "Video", "Lazada")["in_sharepoint"], 0)
        self.assertEqual(self.r.sent(C.EV_REVIEW, code), [], "khong nhac nghiem thu")
        self.assertEqual(self.pm.tasks[t["pm_task"]]["state"], "Done")
        tl = S.detail(F.THU, code, repo=self.r)["timeline"]
        self.assertIn("hoàn tất bổ sung data", tl[0]["text"])
        g = {x["data_type"]: x for x in AS.view_data(self.r, F.THU)["gaps"]}
        self.assertEqual(g["Video"]["platforms"], ["Lazada"], "Shopee/TikTok roi khoi Can bo sung")
        self.assertEqual(g["Video"]["plans"], [])

    def test_proposal_plan_needs_proposer_acceptance(self):
        name = AS.create_proposal(F.THU, prop(platforms=["Shopee"]), repo=self.r)["name"]
        AS.review_proposal(F.LINH, name, C.PROP_APPROVED, repo=self.r)
        code = AS.plan(F.LINH, plan(platforms=["Shopee"], channels=["sharepoint", "dw", "powerbi"], proposal=name),
                       repo=self.r, pm=self.pm)["code"]
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["status"], C.ST_REVIEW)
        self.assertEqual([n["to"] for n in self.r.sent(C.EV_REVIEW, code)], [F.THU])
        self.assertFalse(A.has_data(row(self.r, "Commercial", "Video", "Shopee")), "chua nghiem thu -> o chua doi")
        S.respond(F.THU, code, C.ACC_FAIL, "Thiếu cột view", repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["status"], C.ST_DOING)
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        S.respond(F.THU, code, C.ACC_OK, repo=self.r, pm=self.pm)
        x = row(self.r, "Commercial", "Video", "Shopee")
        self.assertEqual((x["in_sharepoint"], x["in_dw"], x["in_powerbi"]), (1, 1, 1))
        self.assertEqual(self.r.proposal_get(name)["resulting_ticket"], code)
        pv = [p for p in AS.view_data(self.r, F.THU)["proposals"] if p["name"] == name][0]
        self.assertEqual(pv["label"], "Đã duyệt → %s · xong" % code)

    def test_auto_close_flips_too(self):
        name = AS.create_proposal(F.THU, prop(platforms=["Shopee"]), repo=self.r)["name"]
        AS.review_proposal(F.LINH, name, C.PROP_APPROVED, repo=self.r)
        code = AS.plan(F.LINH, plan(platforms=["Shopee"], proposal=name), repo=self.r, pm=self.pm)["code"]
        self.r.at(d(2026, 11, 10), 16)
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 13), 9)
        N.run_daily(self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["acceptance"], C.ACC_AUTO)
        self.assertTrue(A.has_data(row(self.r, "Commercial", "Video", "Shopee")))

    def test_pm_done_closes_team_plan(self):
        code = AS.plan(F.LINH, plan(), repo=self.r, pm=self.pm)["code"]
        task = self.r.get(code)["pm_task"]
        self.r.flags_ = F.Flags()
        P.apply_task(self.r, code, {"workflow_state": "Done"}, F.LINH, pm=self.pm)
        self.assertEqual(self.r.get(code)["status"], C.ST_DONE)
        self.assertTrue(A.has_data(row(self.r, "Commercial", "Video", "TikTok")))
        self.assertNotIn(("state", task, "Done"), self.pm.calls[-1:], "khong day nguoc sang /pm")

    def test_cancel_returns_cell_to_missing(self):
        code = AS.plan(F.LINH, plan(), repo=self.r, pm=self.pm)["code"]
        S.cancel(F.LINH, code, "Đổi sang mua data", repo=self.r, pm=self.pm)
        teams = AS.view_data(self.r, F.THU)["teams"]
        cell = {g["data_type"]: g for g in teams[0]["groups"]}["Video"]["cells"]["Shopee"]
        self.assertEqual((cell["state"], cell["plan"]), ("none", None))
        self.assertFalse(A.has_data(row(self.r, "Commercial", "Video", "Shopee")))
        AS.plan(F.LINH, plan(), repo=self.r, pm=self.pm)     # len lai ke hoach duoc

    def test_detail_extras(self):
        code = AS.plan(F.LINH, plan(method="API sàn"), repo=self.r, pm=self.pm)["code"]
        dv = S.detail(F.LINH, code, repo=self.r)
        self.assertEqual(dv["type_short"], C.DA_TYPE_LABEL)
        self.assertEqual(dv["team"], "Commercial")
        self.assertEqual(dv["plan"], {"platforms": "Shopee, TikTok", "channels": "SharePoint · Data Warehouse",
                                      "method": "API sàn", "team": "Commercial", "data_type": "Video",
                                      "needs_acceptance": False})
        self.assertIn("Hoàn tất (ô chuyển “Có”)", [s["label"] for s in dv["team_statuses"]])
        req = S.detail(F.THU, T.create(self.r, request_type="Crawl data mới"), repo=self.r)
        self.assertNotIn("plan", req)
        self.assertNotIn("library", req)


# ====================================================================== thu vien ==========
class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.r, self.pm, self.c = F.sample()

    def test_auto_add_on_powerbi_accepted(self):
        lib = self.r.library_rows()
        self.assertEqual([(x["title"], x["link"], x["from_ticket"], x["report_owner"], x["team"]) for x in lib],
                         [("Dashboard Stock Boxme", "https://app.powerbi.com/stock", self.c["stock"], F.LINH, "Commercial")],
                         "mau: yeu cau Sua Power BI Dat co link -> tu vao thu vien")
        dv = S.detail(F.DUYEN, self.c["stock"], repo=self.r)
        self.assertEqual(dv["library"]["link"], "https://app.powerbi.com/stock")
        # Chua dat / chua co link / loai khac -> khong them
        self.assertIsNone(S.detail(F.HIEN, self.c["aff"], repo=self.r)["library"], "Cho nghiem thu chua them")
        S.respond(F.HIEN, self.c["aff"], C.ACC_OK, repo=self.r, pm=self.pm)
        self.assertEqual(len(self.r.library_rows()), 2)
        code = T.create(self.r, request_type="Crawl data mới")
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        O.mark_done(F.LINH, code, output_link="https://sp/x", repo=self.r, pm=self.pm)
        S.respond(F.THU, code, C.ACC_OK, repo=self.r, pm=self.pm)
        self.assertEqual(len(self.r.library_rows()), 2, "Crawl khong vao thu vien")
        code = T.create(self.r)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        O.mark_done(F.LINH, code, output_link="https://app.powerbi.com/stock", repo=self.r, pm=self.pm)
        S.respond(F.THU, code, C.ACC_OK, repo=self.r, pm=self.pm)
        self.assertEqual(len(self.r.library_rows()), 2, "trung link -> khong them")
        code = T.create(self.r)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        S.respond(F.THU, code, C.ACC_OK, repo=self.r, pm=self.pm)
        self.assertEqual(len(self.r.library_rows()), 2, "khong co link -> khong them")
        self.assertIsNone(S.detail(F.LINH, code, repo=self.r)["library"], "popup goi y them tay")

    def test_crud_team_only_and_hidden_for_employees(self):
        out = AS.save_library(F.LINH, {"title": "PnL tổng", "link": "https://app.powerbi.com/pnl", "team": "Commercial",
                                       "report_owner": F.DUNG, "from_ticket": self.c["pnl"].lower(), "tags": "PnL"}, repo=self.r)
        x = self.r.library_get(out["name"])
        self.assertEqual((x["from_ticket"], x["added_by"], x["active"]), (self.c["pnl"], F.LINH, 1))
        for bad, msg in (({"title": "a", "link": "https://app.powerbi.com/stock"}, "đã có trong thư viện"),
                         ({"title": "a", "link": "https://x.vn/a", "from_ticket": "DR-1999-0001"}, "Không có yêu cầu"),
                         ({"title": "a", "link": "https://x.vn/a", "report_owner": "ma@x.vn"}, "Người phụ trách"),
                         ({"title": "", "link": "ftp://x"}, "Chưa có tên")):
            with self.assertRaises(S.DataHubError) as cm:
                AS.save_library(F.LINH, bad, repo=self.r)
            self.assertIn(msg, str(cm.exception))
        AS.save_library(F.LINH, {"name": out["name"], "title": "PnL tổng (v2)", "link": "https://app.powerbi.com/pnl"}, repo=self.r)
        self.assertEqual(self.r.library_get(out["name"])["title"], "PnL tổng (v2)", "sua cung link cua chinh no")
        AS.set_library_active(F.LINH, out["name"], 0, repo=self.r)
        self.assertNotIn(out["name"], [x["name"] for x in AS.view_data(self.r, F.THU)["library"]], "nhan vien khong thay muc an")
        self.assertIn(out["name"], [x["name"] for x in AS.view_data(self.r, F.LINH)["library"]], "team Data thay de hien lai")
        self.assertEqual(AS.suggest(F.THU, "PnL tổng v2", repo=self.r)["library"], [], "muc an khong goi y")
        AS.set_library_active(F.LINH, out["name"], "1", repo=self.r)
        self.assertTrue(self.r.library_get(out["name"])["active"])

    def test_suggest(self):
        AS.save_library(F.LINH, {"title": "Dashboard PnL tổng hợp brand", "link": "https://app.powerbi.com/pnl"}, repo=self.r)
        s = AS.suggest(F.THU, "Dashboard PnL theo ngày Friso", repo=self.r)
        self.assertEqual([x["title"] for x in s["library"]], ["Dashboard PnL tổng hợp brand"])
        self.assertEqual([x["code"] for x in s["requests"]], [self.c["pnl"]], "yeu cau dang mo tuong tu")
        self.assertEqual(s["requests"][0]["url"], "/du-lieu?ma=" + self.c["pnl"])
        self.assertEqual(AS.suggest(F.THU, "Dashboard Stock Boxme", repo=self.r)["requests"], [], "yeu cau da dong khong goi y")
        self.assertEqual([x["title"] for x in AS.suggest(F.THU, "stock boxme hang ngay", repo=self.r)["library"]],
                         ["Dashboard Stock Boxme"])
        self.assertEqual(AS.suggest(F.THU, "PB", repo=self.r), {"library": [], "requests": []})
        with self.assertRaises(S.Forbidden):
            AS.suggest(F.OUTSIDER, "PnL", repo=self.r)


# ====================================================================== dong ma tran ======
class TestRowEdit(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = fresh()

    def test_edit_and_create(self):
        x = row(self.r, "Commercial", "Video", "Shopee")
        AS.save_row(F.LINH, {"name": x["name"], "team": "Commercial", "data_type": "Video", "platform": "Shopee",
                             "in_dw": 1, "frequency": C.FREQ_DAILY, "data_owner": F.DUNG, "note": "Crawl tay"}, repo=self.r)
        y = self.r.avail_get(x["name"])
        self.assertEqual((y["in_dw"], y["in_sharepoint"], y["frequency"], y["data_owner"], y["note"]),
                         (1, 0, C.FREQ_DAILY, F.DUNG, "Crawl tay"))
        self.assertEqual(y["last_updated"], self.r.now(), "vua co du lieu lan dau -> ghi ngay cap nhat")
        out = AS.save_row(F.HOAN, {"team": "Media", "data_type": "Meta Ads", "platform": "facebook", "in_sharepoint": "1"},
                          repo=self.r)
        self.assertTrue(out["created"])
        self.assertEqual(self.r.avail_get(out["name"])["platform"], "facebook")
        for bad, msg in (({"team": "Commercial", "data_type": "video", "platform": "tiktok"}, "Đã có dòng"),
                         ({"team": "Media", "data_type": "X", "platform": "Y", "data_owner": "ma@x.vn"}, "Người phụ trách"),
                         ({"name": "AV-999", "team": "Media", "data_type": "X", "platform": "Y"}, "Không tìm thấy dòng")):
            with self.assertRaises(S.DataHubError) as cm:
                AS.save_row(F.LINH, bad, repo=self.r)
            self.assertIn(msg, str(cm.exception))


# ====================================================================== quyen =============
class TestPermissions(unittest.TestCase):
    """Moi viec dot 2 x moi vai: nhan vien / team Data / System Manager / nguoi ngoai."""

    def actions(self, r, pm, name):
        return {
            "page": lambda u: AS.page(u, repo=r),
            "propose": lambda u: AS.create_proposal(u, prop(), repo=r),
            "suggest": lambda u: AS.suggest(u, "PnL brand", repo=r),
            "review": lambda u: AS.review_proposal(u, name, C.PROP_REJECTED, "x", repo=r),
            "plan": lambda u: AS.plan(u, plan(data_type="Live", platforms=["Lazada"], assignee=F.HOAN), repo=r, pm=pm),
            "save_row": lambda u: AS.save_row(u, {"team": "Z", "data_type": u, "platform": "Shopee"}, repo=r),
            "library": lambda u: AS.save_library(u, {"title": "x", "link": "https://x.vn/" + u}, repo=r),
        }

    def test_matrix(self):
        expect = {F.THU: {"page", "propose", "suggest"}, F.LINH: None, F.ADMIN: None, F.OUTSIDER: set()}
        everything = {"page", "propose", "suggest", "review", "plan", "save_row", "library"}
        for user, allowed in expect.items():
            allowed = everything if allowed is None else allowed
            for act in sorted(everything):
                r, pm = fresh()
                name = AS.create_proposal(F.HIEN, prop(), repo=r)["name"]
                fn = self.actions(r, pm, name)[act]
                if act in allowed:
                    fn(user)
                else:
                    with self.assertRaises(S.Forbidden, msg="%s %s" % (user, act)):
                        fn(user)
                    self.assertEqual(r.proposal_get(name)["status"], C.PROP_PENDING)

    def test_guest(self):
        r, _ = fresh()
        with self.assertRaises(S.Forbidden):
            AS.page("Guest", repo=r)


# ====================================================================== trang =============
class TestAvailPage(unittest.TestCase):
    def setUp(self):
        self.r, self.pm, self.c = FA.sample_avail()

    def boot(self, out):
        m = re.search(r'<script type="application/json" id="edh-boot">(.*?)</script>', out, re.S)
        return json.loads(m.group(1))

    def test_employee_view(self):
        out = T.render("san_co", S.avail_page(F.THU, repo=self.r))
        self.assertIn('<a class="edh-tab is-on" href="/du-lieu/san-co" aria-current="page">Data availability</a>', out)
        for s in ("<span>Có trên SharePoint</span><b>73%</b>", "<span>Có trong Data Warehouse</span><b>73%</b>",
                  "<span>Đã dùng trong Power BI</span><b>40%</b>"):
            self.assertIn(s, out)
        self.assertRegex(out, r"Đề xuất chờ duyệt</span><b>1</b>")
        self.assertRegex(out, r"Trễ cập nhật</span><b>1</b>")
        self.assertIn("data-edh-propose", out)
        for team_only in ("data-edh-plan=", "data-edh-plan-cell", "data-edh-approve", "data-edh-row-edit", "data-edh-lib-new",
                          "data-edh-plan-ov", "data-edh-row-new"):
            self.assertNotIn(team_only, out, team_only)
        self.assertIn('<span class="edh-cellno" title="Lazada: chưa có">', out)
        self.assertIn('data-edh-open="%s"' % self.c["da_video"], out, "o dang lam mo popup DA")
        self.assertIn("Đang làm · hạn 24/11", out)
        self.assertIn("Trễ cập nhật · TikTok", out)
        self.assertIn("Chờ duyệt · còn 24h", out)
        self.assertIn("Đã duyệt → %s" % self.c["da_voucher"], out)
        self.assertIn("Facebook chưa có API", out, "ly do tu choi hien cho moi nguoi")
        self.assertIn("Omisell", out)
        self.assertIn('data-edh-av="library" hidden', out)
        b = self.boot(out)
        self.assertEqual((b["page"], b["is_team"], b["sub"]), ("avail", False, "matrix"))
        AS.save_row(F.LINH, {"team": "Commercial", "data_type": T.EVIL, "platform": "Shopee", "note": T.EVIL}, repo=self.r)
        AS.create_proposal(F.THU, prop(data_type=T.EVIL, purpose=T.EVIL), repo=self.r)
        for who in (F.THU, F.LINH):
            out2 = T.render("san_co", S.avail_page(who, repo=self.r))
            self.assertNotIn(T.EVIL, out2)
            self.assertIn("&lt;script&gt;", out2)
            self.assertNotIn("</script><script>", out2)
        self.assertNotIn("rows", b, "nhan vien khong nhan du lieu sua")
        self.assertNotIn("</script><script>", out)

    def test_team_view_and_boot(self):
        out = T.render("san_co", S.avail_page(F.LINH, repo=self.r))
        self.assertIn("data-edh-plan-ov", out)
        self.assertIn('data-edh-approve="%s"' % self.c["p_creator"], out)
        self.assertNotIn('data-edh-approve="%s"' % self.c["p_kol"], out, "da quyet -> khong con nut")
        lazada = row(self.r, "Commercial", "Live", "Lazada")
        self.assertIn('data-edh-plan-cell="%s"' % lazada["name"], out)
        self.assertIn('data-edh-row-edit="%s"' % row(self.r, "Commercial", "Product", "Shopee")["name"], out)
        b = self.boot(out)
        self.assertEqual(len(b["rows"]), 52, "de xuat duyet cho san da co dong -> khong tao them; bi tu choi -> khong tao")
        self.assertEqual(b["plan_defaults"], {"start": "2026-11-09", "due": "2026-11-18", "sla_days": 7, "priority": C.PRI_NORMAL})
        aff = b["gaps"]["Service|Affiliate order"]
        self.assertEqual((aff["proposal"], aff["urgency"], aff["platforms"]), (self.c["p_gmv"], C.PRI_HIGH, ["TikTok", "Lazada"]))
        self.assertEqual(b["gaps"]["Commercial|Voucher & Flashsale"]["proposal"], "", "de xuat da co ke hoach")
        self.assertIn("data-edh-plan=\"Service|Affiliate order\"", out)

    def test_library_view_and_prefill(self):
        out = T.render("san_co", S.avail_page(F.THU, view="thu-vien", repo=self.r))
        self.assertIn('data-edh-av="matrix" hidden', out)
        self.assertNotIn('data-edh-av="library" hidden', out)
        self.assertIn("Dashboard Stock Boxme ↗", out)
        self.assertIn('data-edh-open="%s"' % self.c["stock"], out)
        self.assertIn('Thư viện báo cáo <span class="edh-cnt">3</span>', out)
        ctx = S.avail_page(F.LINH, prefill_ticket=self.c["aff"].lower(), repo=self.r)
        b = json.loads(ctx["boot_json"])
        self.assertEqual((b["sub"], b["prefill"]["from_ticket"], b["prefill"]["link"]), ("library", self.c["aff"], "https://app.powerbi.com/aff"))
        self.assertNotIn("prefill", json.loads(S.avail_page(F.THU, prefill_ticket=self.c["aff"], repo=self.r)["boot_json"]),
                         "chi team Data")

    def test_index_has_suggest_box(self):
        out = T.render("index", S.index_page(F.THU, repo=self.r))
        self.assertIn('data-edh-similar aria-live="polite" hidden', out)


# ====================================================================== hooks / api / doctype
class TestWiring(unittest.TestCase):
    def test_cron_appended_and_function_exists(self):
        src = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertTrue(src.rstrip().endswith('.append("ecentric_workspace.data_hub.avail_service.daily")'), "noi cuoi hooks")
        ns = T.TestHooksAppendOnly().exec_hooks()
        cron = ns["scheduler_events"]["cron"]["0 9 * * *"]
        self.assertIn("ecentric_workspace.data_hub.notify.daily", cron)
        self.assertIn("ecentric_workspace.data_hub.avail_service.daily", cron)
        tree = ast.parse(io.open(os.path.join(APP, "data_hub", "avail_service.py"), encoding="utf-8").read())
        self.assertIn("daily", [n.name for n in tree.body if isinstance(n, ast.FunctionDef)])

    def test_api_writes_are_post_and_no_user_param(self):
        tree = ast.parse(io.open(os.path.join(APP, "data_hub", "api.py"), encoding="utf-8").read())
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in ("propose", "review_proposal", "plan_availability", "save_availability", "save_library", "library_active"):
            dec = ast.dump(fns[name].decorator_list[0])
            self.assertIn("POST", dec, name)
        for name in ("plan_defaults", "suggest", "download_proposal_file"):
            self.assertIn("whitelist", ast.dump(fns[name].decorator_list[0]))
        for n in fns.values():
            self.assertNotIn("user", [a.arg for a in n.args.args], n.name)

    def test_doctype_options_match_constants(self):
        def load(slug):
            j = json.load(io.open(os.path.join(APP, "data_hub", "doctype", slug, slug + ".json"), encoding="utf-8"))
            return j, {x["fieldname"]: x for x in j["fields"]}
        j, f = load("ec_data_availability")
        self.assertEqual(f["frequency"]["options"].split("\n")[1:], list(C.FREQUENCIES))
        for k in C.CHANNEL_KEYS:
            self.assertEqual(f[C.CHANNEL_FIELD[k]]["fieldtype"], "Check")
        j, f = load("ec_data_proposal")
        self.assertEqual(f["status"]["options"].split("\n"), list(C.PROP_STATUSES))
        self.assertEqual(sorted(f["urgency"]["options"].split("\n")), sorted(C.PROP_URGENCIES))
        j, f = load("ec_report_library")
        self.assertNotIn("owner", f, "owner la truong he thong cua Frappe")
        from ecentric_workspace.data_hub import avail_repository as AR  # noqa: F401 (import duoc voi frappe gia)
        for fl, slug in ((AR.AVAIL_FIELDS, "ec_data_availability"), (AR.PROPOSAL_FIELDS, "ec_data_proposal"),
                         (AR.LIBRARY_FIELDS, "ec_report_library")):
            _, f = load(slug)
            self.assertEqual([x for x in fl if x not in f and x not in ("name", "creation", "modified")], [], slug)
        self.assertEqual(load("ec_data_ticket")[1]["method"]["options"].split("\n")[1:], list(C.METHODS))


# ====================================================================== fixture jsdom ===
def fixture_pages():
    r, pm, c = FA.sample_avail()
    pages = {"avail_user": T.render("san_co", S.avail_page(F.THU, repo=r)),
             "avail_team": T.render("san_co", S.avail_page(F.LINH, repo=r)),
             "avail_team_lib": T.render("san_co", S.avail_page(F.LINH, view="thu-vien", repo=r)),
             "index_suggest": T.render("index", S.index_page(F.THU, repo=r))}
    api = {"codes": c,
           "details": {code: {u: S.detail(u, code, repo=r) for u in (F.THU, F.LINH)} for code in (c["da_video"], c["da_voucher"], c["stock"])},
           "suggest": AS.suggest(F.THU, "Dashboard PnL theo ngày Friso", repo=r),
           "plan_defaults": AS.plan_defaults(r, "2026-11-12", C.PRI_HIGH)}
    return pages, api


class TestAvailFixtures(unittest.TestCase):
    def test_fixtures_current(self):
        pages, api = fixture_pages()
        files = {name + ".html": html for name, html in pages.items()}
        files["avail_api.json"] = json.dumps(api, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
        if os.environ.get("EDH_UPDATE_FIXTURES"):
            for name, text in files.items():
                with io.open(os.path.join(FIX, name), "w", encoding="utf-8") as fh:
                    fh.write(text)
        for name, text in files.items():
            p = os.path.join(FIX, name)
            self.assertTrue(os.path.isfile(p), "thieu fixture %s - chay voi EDH_UPDATE_FIXTURES=1" % name)
            self.assertEqual(io.open(p, encoding="utf-8").read(), text, "fixture %s cu - EDH_UPDATE_FIXTURES=1" % name)


if __name__ == "__main__":
    unittest.main()
