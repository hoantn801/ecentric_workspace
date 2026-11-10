# Copyright (c) 2026, eCentric and contributors
"""Phan dot 2 cua repo gia (FakeRepo ke thua mixin nay): dung cac ham avail_ / proposal_ / library_ cua
data_hub.avail_repository. sample_avail(repo) dung bo du lieu dot 2 QUA SERVICE THAT tren repo cua
fake.sample(): seed 52 dong (patch p002), de xuat cho duyet / da duyet / tu choi, ke hoach DA dang lam,
thu vien bao cao, do tuoi.
"""
import copy
import datetime as dt
import itertools


class FakeAvailMixin(object):
    def _av(self):
        if not hasattr(self, "_avail_store"):
            self._avail_store = {"rows": {}, "props": {}, "lib": {}, "seq": itertools.count(1),
                                 "pseq": itertools.count(1), "lseq": itertools.count(1), "tick": itertools.count(1)}
        return self._avail_store

    def _stamp_av(self):
        # thu tu tao on dinh (creation tang dan ke ca cung mot thoi diem)
        n = next(self._av()["tick"])
        return (self.clock + dt.timedelta(microseconds=n)).strftime("%Y-%m-%d %H:%M:%S.%f")

    # ---- availability
    def avail_rows(self):
        return sorted((copy.deepcopy(r) for r in self._av()["rows"].values()), key=lambda r: (r["creation"], r["name"]))

    def avail_get(self, name):
        r = self._av()["rows"].get(name)
        return copy.deepcopy(r) if r else None

    def avail_lock(self, names):
        self.locks.append(("avail", tuple(names)))
        return [copy.deepcopy(self._av()["rows"][n]) for n in names if n in self._av()["rows"]]

    def avail_insert(self, values):
        name = "AV-%03d" % next(self._av()["seq"])
        row = {"in_sharepoint": 0, "in_dw": 0, "in_powerbi": 0, "front_priority": 0, "note": "", "last_updated": None,
               "frequency": "", "data_owner": None, "planned_ticket": None}
        row.update(copy.deepcopy(values))
        row.update({"name": name, "creation": self._stamp_av(), "modified": self._stamp_av()})
        self._av()["rows"][name] = row
        return name

    def avail_set(self, name, values):
        self._av()["rows"][name].update(copy.deepcopy(values))
        self._av()["rows"][name]["modified"] = self._stamp_av()

    # ---- de xuat
    def proposal_rows(self, limit=0):
        rows = sorted((copy.deepcopy(p) for p in self._av()["props"].values()), key=lambda p: p["creation"], reverse=True)
        return rows[:limit] if limit else rows

    def proposal_pending(self):
        return [p for p in self.proposal_rows() if p["status"] == "Chờ duyệt"]

    def proposal_get(self, name):
        p = self._av()["props"].get(name)
        return copy.deepcopy(p) if p else None

    def proposal_lock(self, name):
        self.locks.append(("proposal", name))
        return self.proposal_get(name)

    def proposal_by_ticket(self, code):
        for p in self._av()["props"].values():
            if code and p.get("resulting_ticket") == code:
                return copy.deepcopy(p)
        return None

    def proposal_sent_today(self, user, day):
        return sum(1 for p in self._av()["props"].values() if p["proposer"] == user and p["creation"][:10] == str(day))

    def proposal_insert(self, values):
        name = "DP-%d-%04d" % (self.today().year, next(self._av()["pseq"]))
        p = {"decided_by": None, "decided_at": None, "reason": "", "resulting_ticket": None, "urgency_note": "",
             "department": "", "frequency": "", "needed_by": None, "urgency_reason": "", "data_from": None,
             "data_to": None, "channels": "", "source_links": "", "scope": ""}
        p.update(copy.deepcopy(values))
        p.update({"name": name, "creation": self._stamp_av(), "modified": self._stamp_av()})
        self._av()["props"][name] = p
        return name

    def proposal_set(self, name, values):
        self._av()["props"][name].update(copy.deepcopy(values))

    def proposal_add_files(self, name, files, by):
        out = []
        store = self._av().setdefault("pfiles", {})
        for f in files or ():
            n = "PF-%d" % (len(store) + 1)
            store[n] = {"name": n, "parent": name, "file_name": f["name"], "file_size": f.get("size") or 0,
                        "content": f.get("content") or b"x", "uploaded_by": by}
            out.append(n)
        return out

    def proposal_files(self, names):
        out = {}
        for f in self._av().get("pfiles", {}).values():
            if f["parent"] in (names or ()):
                out.setdefault(f["parent"], []).append({"name": f["name"], "file_name": f["file_name"],
                                                        "file_size": f["file_size"]})
        return out

    def proposal_file_content(self, name, row):
        f = self._av().get("pfiles", {}).get(row)
        if not f or f["parent"] != name:
            return None
        return f["file_name"], f["content"]

    def departments(self):
        """Phong ban ERP gia: moi phong ban cua nhan vien mau + Media (chua ai) + mot phong trung ten khac cong ty."""
        names = sorted(set(self.emps.values()) | {"Media - EC", "Service - BM"})
        return [{"name": n, "label": n.rsplit(" - ", 1)[0]} for n in names]

    # ---- thu vien
    def library_rows(self, include_inactive=False):
        rows = [copy.deepcopy(x) for x in self._av()["lib"].values() if include_inactive or x.get("active")]
        return sorted(rows, key=lambda x: x["modified"], reverse=True)

    def library_get(self, name):
        x = self._av()["lib"].get(name)
        return copy.deepcopy(x) if x else None

    def library_by_link(self, link):
        return next((copy.deepcopy(x) for x in self._av()["lib"].values() if link and x.get("link") == link), None)

    def library_by_ticket(self, code):
        return next((copy.deepcopy(x) for x in self._av()["lib"].values() if code and x.get("from_ticket") == code), None)

    def library_insert(self, values):
        name = "RL-%05d" % next(self._av()["lseq"])
        x = {"team": "", "data_sources": "", "from_ticket": None, "tags": "", "active": 1, "report_owner": None,
             "added_by": None}
        x.update(copy.deepcopy(values))
        x.update({"name": name, "creation": self._stamp_av(), "modified": self._stamp_av()})
        self._av()["lib"][name] = x
        return name

    def library_set(self, name, values):
        self._av()["lib"][name].update(copy.deepcopy(values))
        self._av()["lib"][name]["modified"] = self._stamp_av()

    # ---- tien ich test
    def avail_find(self, team, data_type, platform):
        for r in self.avail_rows():
            if (r["team"], r["data_type"], r["platform"]) == (team, data_type, platform):
                return r
        return None


def seed(repo):
    """52 dong cua patch p002 (dung ham rows() cua patch)."""
    from ecentric_workspace.data_hub.patches import p002_seed_data_availability as P
    for r in P.rows():
        repo.avail_insert(r)
    return repo


def sample_avail(repo=None, pm=None):
    """Bo mau dot 2 tren fake.sample() (hom nay = thu Hai 09/11/2026, 09:30). -> (repo, pm, codes)."""
    from ecentric_workspace.data_hub import avail_service as AS
    from ecentric_workspace.data_hub import constants as C
    from ecentric_workspace.data_hub.tests import fake as F
    if repo is None:
        repo, pm, codes = F.sample()
    else:
        codes = {}
    seed(repo)
    now = repo.clock
    # do tuoi: vai dong co tan suat / nguoi phu trach / ngay cap nhat
    for (team, dtype, plat), freq, last, owner in (
            (("Commercial", "Orderline", "Shopee"), C.FREQ_DAILY, now - dt.timedelta(hours=10), F.LINH),
            (("Commercial", "Orderline", "TikTok"), C.FREQ_DAILY, now - dt.timedelta(days=4), F.LINH),
            (("Commercial", "Product", "Shopee"), C.FREQ_WEEKLY, now - dt.timedelta(days=3), F.DUNG),
            (("Boxme Data", "Stock Report", "Oms Boxme"), C.FREQ_HOURLY, now - dt.timedelta(hours=2), F.HOAN)):
        r = repo.avail_find(team, dtype, plat)
        repo.avail_set(r["name"], {"frequency": freq, "last_updated": last, "data_owner": owner})
    repo.avail_set(repo.avail_find("Commercial", "Orderline", "Shopee")["name"], {"note": "Cập nhật 06:00 mỗi ngày"})
    # de xuat: cho duyet (con han / qua han), da duyet -> ke hoach, tu choi
    repo.at(dt.date(2026, 11, 6), 15, 20)
    codes["p_voucher"] = AS.create_proposal(F.THU, {"department": "Commercial - EC", "data_type": "Voucher & Flashsale",
                                                    "platforms": ["Shopee", "TikTok"], "purpose": "Đo hiệu quả voucher theo ngày cho 12.12",
                                                    "urgency": C.PRI_HIGH, "urgency_reason": "Cần số trước khi chốt ngân sách 12.12",
                                                    "frequency": C.FREQ_DAILY, "needed_by": "2026-12-01T17:00",
                                                    "source_links": "https://seller.shopee.vn/portal/marketing/vouchers\nhttps://seller-vn.tiktok.com/promotion",
                                                    "scope": "12 brand Commercial, toàn bộ voucher shop + flashsale",
                                                    "data_from": "2026-10-01", "channels": ["dw", "powerbi"]},
                                    files=[{"name": "huong-dan-voucher.png", "content": b"PNG", "size": 3}], repo=repo)["name"]
    repo.at(dt.date(2026, 11, 9), 9, 5)
    codes["p_creator"] = AS.create_proposal(F.HIEN, {"department": "Service - EC", "data_type": "Affiliate creator orders",
                                                     "platforms": ["TikTok"], "purpose": "Đối soát hoa hồng creator",
                                                     "urgency": C.PRI_NORMAL, "frequency": C.FREQ_WEEKLY}, repo=repo)["name"]
    codes["p_kol"] = AS.create_proposal(F.DUYEN, {"department": "Commercial - EC", "data_type": "KOL booking",
                                                  "platforms": [], "other_platform": "Facebook",
                                                  "purpose": "Theo dõi chi phí KOL", "urgency": C.PRI_NORMAL,
                                                  "frequency": C.PROP_FREQ_ONCE}, repo=repo)["name"]
    codes["p_gmv"] = AS.create_proposal(F.HIEN, {"department": "Service - EC", "data_type": "Affiliate order",
                                                 "platforms": ["TikTok", "Lazada"], "purpose": "Báo cáo affiliate 3 sàn",
                                                 "urgency": C.PRI_HIGH, "urgency_reason": "Khách hỏi số affiliate trong QBR tuần sau",
                                                 "frequency": C.FREQ_DAILY, "channels": ["sharepoint", "powerbi"],
                                                 "source_links": "https://affiliate.tiktok.com/connection/orders",
                                                 "scope": "Shop Friso, Enfa", "data_from": "2026-09-01", "data_to": "2026-11-30"}, repo=repo)["name"]
    AS.review_proposal(F.LINH, codes["p_kol"], C.PROP_REJECTED, "Facebook chưa có API, dùng file tay của Media", repo=repo)
    AS.review_proposal(F.LINH, codes["p_gmv"], C.PROP_APPROVED, repo=repo)
    # ke hoach DA: Video (team tu len), Voucher (tu de xuat cua Thu - duyet roi len ke hoach)
    repo.at(dt.date(2026, 11, 9), 9, 15)
    codes["da_video"] = AS.plan(F.LINH, {"team": "Commercial", "data_type": "Video", "platforms": ["Shopee", "TikTok", "Lazada"],
                                         "channels": ["sharepoint", "dw", "powerbi"], "assignee": F.LINH, "method": "Crawl",
                                         "start_date": "2026-11-12"}, repo=repo, pm=pm)["code"]
    repo.at(dt.date(2026, 11, 9), 9, 20)
    AS.review_proposal(F.HOAN, codes["p_voucher"], C.PROP_APPROVED, "Ưu tiên cho 12.12", repo=repo)
    codes["da_voucher"] = AS.plan(F.HOAN, {"team": "Commercial", "data_type": "Voucher & Flashsale",
                                           "platforms": ["Shopee", "TikTok", "Lazada"], "channels": ["sharepoint", "dw", "powerbi"],
                                           "assignee": F.HOAN, "method": "API sàn", "start_date": "2026-11-11",
                                           "proposal": codes["p_voucher"]}, repo=repo, pm=pm)["code"]
    # thu vien: muc tu yeu cau Power BI da nghiem thu (stock - tu dong) + muc team Data them tay
    AS.save_library(F.LINH, {"title": "Dashboard PnL tổng hợp brand", "link": "https://app.powerbi.com/pnl-tong",
                             "report_owner": F.LINH, "team": "Commercial", "data_sources": "Orderline, Finance",
                             "tags": "PnL, brand"}, repo=repo)
    AS.save_library(F.DUNG, {"title": "Affiliate TikTok theo creator", "link": "https://app.powerbi.com/aff-creator",
                             "report_owner": F.DUNG, "team": "Service", "data_sources": "Traffic affiliate",
                             "tags": "affiliate"}, repo=repo)
    repo.at(dt.date(2026, 11, 9), 9, 30)
    return repo, pm, codes
