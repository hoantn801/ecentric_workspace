# Copyright (c) 2026, eCentric and contributors
"""Repo gia + PM gia cho test Trung tam Du lieu (khong can bench / DB / frappe).

FakeRepo co DUNG cac ham ma service / ops_service / pm_sync / notify goi tren data_hub.repository;
FakePM co dung 4 ham cua data_hub.pm_gateway. sample(repo) dung bo du lieu mau QUA SERVICE THAT
(tao -> nhan -> doi han -> tam dung -> hoan tat ...) cho test trang, fixture jsdom va ban xem thu.
"""
import copy
import datetime as dt
import itertools
import json
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# ngay_lam_viec (helper chung) import frappe o dau module; may khong co frappe -> module rong.
try:
    import frappe  # noqa: F401
except ImportError:
    sys.modules.setdefault("frappe", types.ModuleType("frappe"))

from ecentric_workspace.data_hub import constants as C  # noqa: E402
from ecentric_workspace.data_hub.tests.fake_avail import FakeAvailMixin  # noqa: E402  (ham dot 2)

LINH = "linh.vuong@ecentric.vn"      # team Data
HOAN = "hoan.tran@ecentric.vn"       # team Data + nguoi duyet quy tac
DUNG = "dung.pham@ecentric.vn"       # team Data
THU = "thu.nguyen@ecentric.vn"       # Commercial - nguoi gui
HIEN = "hien.nguyen@ecentric.vn"     # Service
DUYEN = "duyen.le@ecentric.vn"       # Commercial
ADMIN = "admin@ecentric.vn"          # System Manager, khong o team Data
OUTSIDER = "khach@x.vn"              # co tai khoan, khong co ho so Employee
NAMES = {LINH: "Linh Vương", HOAN: "Hoàn Trần", DUNG: "Dũng Phạm", THU: "Thu Nguyễn", HIEN: "Hiền Nguyễn",
         DUYEN: "Duyên Lê", ADMIN: "Quản trị"}
DEPTS = {LINH: "Data - EC", HOAN: "Data - EC", DUNG: "Data - EC", THU: "Commercial - EC", HIEN: "Service - EC",
         DUYEN: "Commercial - EC", ADMIN: "Management - EC"}
MON = dt.date(2026, 11, 9)           # thu Hai - "hom nay" cua bo mau
HOLIDAYS = {dt.date(2026, 11, 20)}   # mot ngay le gia (thu Sau) de test ngay lam viec


class Flags(object):
    pass


class FakeRepo(FakeAvailMixin):
    def __init__(self, today=MON, team=(LINH, HOAN, DUNG), pm_project="PROJ-0042", sync=1):
        self.clock = dt.datetime.combine(today, dt.time(9, 30))
        self.team = list(team)
        self.role_map = {u: {"Employee"} for u in DEPTS}
        for u in team:
            self.role_map.setdefault(u, set()).add(C.DEFAULT_DATA_TEAM_ROLE)
        self.role_map[ADMIN] = {"Employee", "System Manager"}
        self.role_map[OUTSIDER] = set()
        self.emps = dict(DEPTS)
        self.settings_ = {"data_team_role": C.DEFAULT_DATA_TEAM_ROLE, "rule_approver": HOAN,
                          "pm_project": pm_project, "pm_sync_enabled": sync, "active_rule_set": "SLA-v1"}
        self.rule = {"name": "SLA-v1", "version_no": 1, "status": C.RULE_ACTIVE, "effective_from": "2026-11-01",
                     "mult_urgent": 0.5, "mult_high": 0.8, "mult_normal": 1, "mult_low": 1.5,
                     "items": [{"rule_key": k, "label": lab, "days": d, "note": n} for k, _t, lab, d, n in C.RULE_DEFAULTS]}
        self.hol = set(HOLIDAYS)
        self.off = set()                 # (user, date) dang nghi
        self.tickets, self.logs_, self.msgs, self.files = {}, [], [], {}
        self.notes, self.errors = [], []
        self.seq = itertools.count(1)
        self.mseq = itertools.count(1)
        self.flags_ = Flags()
        self.locks = []

    # ---- he thong
    def today(self): return self.clock.date()
    def now(self): return self.clock
    def advance(self, days=0, hours=0):
        self.clock += dt.timedelta(days=days, hours=hours)
    def at(self, d, h=9, m=30):
        self.clock = dt.datetime.combine(d, dt.time(h, m))
    def log_error(self, title): self.errors.append(title)
    def flags(self): return self.flags_
    def commit(self): pass
    def is_duplicate(self, e): return False

    # ---- nguoi dung / cau hinh
    def settings(self): return dict(self.settings_)
    def roles(self, user): return set(self.role_map.get(user, set()))
    def is_admin(self, user): return "System Manager" in self.roles(user)
    def employee(self, user): return {"name": "EMP-" + user, "department": self.emps[user]} if user in self.emps else None
    def full_names(self, users): return {u: NAMES.get(u, u) for u in users or () if u}
    def enabled_users(self, users): return {u for u in users or () if u in NAMES or u in self.role_map}
    def users_with_role(self, role): return sorted(u for u, r in self.role_map.items() if role in r)
    def people(self, q, limit=10):
        q = (q or "").lower()
        return [{"user": u, "name": n, "dept": DEPTS.get(u, "")} for u, n in sorted(NAMES.items())
                if q in n.lower() or q in u][:limit]
    def rule_set(self, name=None): return copy.deepcopy(self.rule)
    def rule_history(self, limit=20):
        return [{"name": self.rule["name"], "version_no": 1, "status": self.rule["status"],
                 "effective_from": self.rule["effective_from"], "reason": "Bộ quy tắc đầu tiên"}]
    def holidays(self): return set(self.hol)
    def is_off_today(self, user, day=None): return (user, day or self.today()) in self.off

    # ---- yeu cau
    def _full(self, code):
        t = copy.deepcopy(self.tickets[code])
        t["attachments"] = [copy.deepcopy(f) for f in self.files.values() if f["parent"] == code]
        return t

    def get(self, code):
        return self._full(code) if code in self.tickets else None

    def lock(self, code):
        self.locks.append(code)
        return self.get(code)

    def _match(self, t, filters):
        for k, v in (filters or {}).items():
            cur = t.get(k)
            if isinstance(v, list):
                op, arg = v
                if op == "in" and cur not in arg:
                    return False
            elif cur != v:
                return False
        return True

    def list_rows(self, filters=None, limit=0, fields=None, order_by="creation desc"):
        rows = [self._full(c) for c, t in self.tickets.items() if self._match(t, filters)]
        rows.sort(key=lambda r: str(r["creation"]), reverse=True)
        for r in rows:
            r.pop("attachments", None)
        return rows[:limit] if limit else rows

    def open_rows(self): return self.list_rows({"status": ["in", list(C.OPEN)]})
    def find_by_pm_task(self, task):
        for c, t in self.tickets.items():
            if task and t.get("pm_task") == task:
                return c
        return None
    def sent_today(self, user, day):
        return sum(1 for t in self.tickets.values() if t["requester"] == user and str(t["creation"])[:10] == str(day))
    def follower_map(self, codes):
        return {c: [f["user"] for f in self.tickets[c]["followers"]] for c in codes if c in self.tickets}

    def insert_ticket(self, values, files=None):
        prefix = "DR" if values.get("kind", C.KIND_REQUEST) == C.KIND_REQUEST else "DA"
        code = "%s-%d-%04d" % (prefix, self.today().year, next(self.seq))
        t = {f: None for f in ("priority", "assignee", "start_date", "due_date", "original_due_date", "accepted_at",
                               "accepted_by", "done_at", "closed_at", "acceptance", "paused_since", "pm_task",
                               "output_link", "cancel_reason", "legacy_ref", "priority_confirmed_by",
                               "reminded_review_on")}
        t.update({"due_change_count": 0, "reject_count": 0, "paused_seconds": 0, "paused_days": 0})
        t.update(copy.deepcopy(values))
        t.update({"name": code, "creation": self.clock.strftime("%Y-%m-%d %H:%M:%S"),
                  "modified": self.clock.strftime("%Y-%m-%d %H:%M:%S"), "followers": []})
        self.tickets[code] = t
        if files:
            self.add_files(code, files, values.get("requester"))
        return code

    def set_fields(self, code, values):
        self.tickets[code].update(copy.deepcopy(values))
        self.tickets[code]["modified"] = self.clock.strftime("%Y-%m-%d %H:%M:%S")

    def add_follower(self, code, user, by):
        fl = self.tickets[code]["followers"]
        if any(f["user"] == user for f in fl):
            return False
        fl.append({"name": "F%d" % (len(fl) + 1), "user": user, "added_by": by})
        return True

    def remove_follower(self, code, user):
        self.tickets[code]["followers"] = [f for f in self.tickets[code]["followers"] if f["user"] != user]

    def add_files(self, code, files, by, message=None):
        out = []
        for f in files or ():
            n = "FILE-%d" % (len(self.files) + 1)
            self.files[n] = {"name": n, "parent": code, "file_url": "/private/files/" + f["name"], "file_name": f["name"],
                             "file_size": f.get("size") or len(f.get("content") or b""), "message": message or "",
                             "uploaded_by": by, "content": f.get("content") or b"x"}
            out.append(n)
        return out

    def file_content(self, code, row):
        f = self.files.get(row)
        if not f or f["parent"] != code:
            return None
        return f["file_name"], f["content"]

    def insert_log(self, values):
        row = dict(values, name="LOG-%d" % (len(self.logs_) + 1), creation=self.clock.strftime("%Y-%m-%d %H:%M:%S"))
        self.logs_.append(row)
        return row["name"]

    def logs(self, code):
        return [dict(lg) for lg in reversed(self.logs_) if lg["ticket"] == code]

    def insert_message(self, values):
        row = dict(values, name="MSG-%d" % next(self.mseq), creation=self.clock.strftime("%Y-%m-%d %H:%M:%S"))
        self.msgs.append(row)
        return row["name"]

    def messages(self, code):
        return [dict(m) for m in self.msgs if m["ticket"] == code]

    def notify(self, event, recipient, title, message, url, code, dedupe_key, actor=None):
        self.notes.append({"event": event, "to": recipient, "title": title, "message": message, "url": url,
                           "code": code, "key": dedupe_key, "actor": actor})
        return {"ok": True}

    # ---- tien ich test
    def events(self, code=None):
        return [lg["event"] for lg in self.logs_ if code is None or lg["ticket"] == code]

    def sent(self, event=None, code=None):
        return [n for n in self.notes if (event is None or n["event"] == event) and (code is None or n["code"] == code)]


class PMError(Exception):
    pass


class FakePM(object):
    """4 ham cua pm_gateway, ghi lai moi lan goi; fail = {ten_ham} -> nem loi."""

    def __init__(self, repo=None):
        self.calls, self.tasks, self.fail, self.repo = [], {}, set(), repo
        self.seq = itertools.count(1)
        self.saw_flag = []

    def _flag(self):
        if self.repo is not None:
            from ecentric_workspace.data_hub import pm_sync
            self.saw_flag.append(pm_sync.busy(self.repo))

    def create_task(self, project, subject, description, assignee, start, due, priority):
        self._flag()
        self.calls.append(("create", project, subject, assignee, start, due, priority))
        if "create" in self.fail:
            raise PMError("PM tạo task lỗi")
        name = "TASK-2026-%05d" % next(self.seq)
        self.tasks[name] = {"project": project, "subject": subject, "description": description, "assignee": assignee,
                            "exp_start_date": start, "exp_end_date": due, "priority": priority, "state": "To Do"}
        return name

    def update_task(self, task, **fields):
        self._flag()
        self.calls.append(("update", task, dict(fields)))
        if "update" in self.fail:
            raise PMError("PM sửa task lỗi")
        self.tasks[task].update(fields)

    def set_assignee(self, task, new, old=None):
        self._flag()
        self.calls.append(("assignee", task, new, old))
        if "assignee" in self.fail:
            raise PMError("PM giao việc lỗi")
        self.tasks[task]["assignee"] = new

    def set_state(self, task, state):
        self._flag()
        self.calls.append(("state", task, state))
        if "state" in self.fail:
            raise PMError("Không thể hoàn thành nhiệm vụ khi vẫn còn nhiệm vụ con chưa đóng.")
        self.tasks[task]["state"] = state


def req(**kw):
    d = {"request_type": "Power BI mới", "proposed_priority": C.PRI_NORMAL, "title": "Dashboard PnL theo ngày",
         "description": "Cần dashboard PnL theo ngày cho brand Friso trên Shopee + TikTok.", "data_used": "Orderline",
         "reference_link": "", "urgent_reason": ""}
    d.update(kw)
    return d


def sample(repo=None, pm=None):
    """Bo du lieu mau ~ mockup (hom nay = thu Hai 09/11/2026). -> (repo, pm, {ten: ma})."""
    from ecentric_workspace.data_hub import ops_service as O
    from ecentric_workspace.data_hub import service as S
    repo = repo or FakeRepo()
    pm = pm or FakePM(repo)
    codes = {}

    def mk(key, user, day, hour=10, **kw):
        repo.at(day, hour)
        codes[key] = S.create(user, req(**kw), repo=repo)["code"]
        return codes[key]

    # Hoan tat 3 ngay truoc, dung han
    mk("stock", DUYEN, dt.date(2026, 10, 27), title="Dashboard Stock Boxme", request_type="Sửa Power BI có sẵn",
       proposed_priority=C.PRI_HIGH)
    repo.at(dt.date(2026, 10, 28))
    O.accept(LINH, codes["stock"], LINH, repo=repo, pm=pm)
    repo.at(dt.date(2026, 10, 30), 16)
    O.mark_done(LINH, codes["stock"], output_link="https://app.powerbi.com/stock", repo=repo, pm=pm)
    repo.at(dt.date(2026, 11, 2), 9)
    S.respond(DUYEN, codes["stock"], C.ACC_OK, repo=repo, pm=pm)
    # Dang xu ly - qua han, da doi han 1 lan
    mk("pnl", THU, dt.date(2026, 10, 28), 16, title="Power BI PnL cho brand mới (Friso)", proposed_priority=C.PRI_HIGH,
       data_used="Orderline · Finance (Shopee, TikTok)", reference_link="https://example.com/mau-pnl")
    repo.at(dt.date(2026, 10, 29), 9)
    O.accept(LINH, codes["pnl"], LINH, due_date="2026-11-03", reason="Người gửi cần trước 03/11 để họp brand",
             repo=repo, pm=pm)
    S.send_message(THU, codes["pnl"], "Mẫu giống Abbott nha em, thêm cột voucher nếu được.", repo=repo)
    repo.at(dt.date(2026, 11, 3), 10)
    O.update(LINH, codes["pnl"], {"due_date": "2026-11-06", "reason": "Chờ brand gửi file mapping SKU",
                                  "note": "Đã xong 70%, còn trang Chi phí."}, repo=repo, pm=pm)
    # Dang xu ly - con han
    mk("rating", DUYEN, dt.date(2026, 11, 3), title="Crawl Product Rating Lazada", request_type="Crawl data mới")
    repo.at(dt.date(2026, 11, 4), 9)
    O.accept(LINH, codes["rating"], LINH, repo=repo, pm=pm)
    mk("misa", HIEN, dt.date(2026, 11, 4), title="Ghép data Misa + e-Invoice", request_type="Xử lý dữ liệu")
    repo.at(dt.date(2026, 11, 6), 9)
    O.accept(HOAN, codes["misa"], HOAN, repo=repo, pm=pm)
    # Tam dung - cho nguoi gui
    mk("live", THU, dt.date(2026, 11, 2), title="Báo cáo Live TikTok")
    repo.at(dt.date(2026, 11, 3), 9)
    O.accept(LINH, codes["live"], LINH, repo=repo, pm=pm)
    repo.at(dt.date(2026, 11, 5), 14)
    O.pause(LINH, codes["live"], note="Chờ Commercial gửi quyền truy cập TikTok Shop.", repo=repo, pm=pm)
    # Cho nghiem thu
    mk("aff", HIEN, dt.date(2026, 11, 2), title="Dashboard Affiliate TikTok", request_type="Sửa Power BI có sẵn")
    repo.at(dt.date(2026, 11, 3), 9)
    O.accept(DUNG, codes["aff"], DUNG, repo=repo, pm=pm)
    repo.at(dt.date(2026, 11, 6), 17)
    O.mark_done(DUNG, codes["aff"], output_link="https://app.powerbi.com/aff", repo=repo, pm=pm)
    # Cho tiep nhan: Khan (de xuat), binh thuong, thap
    mk("voucher", THU, dt.date(2026, 11, 9), 8, title="Crawl Voucher & Flashsale Shopee", request_type="Crawl data mới",
       proposed_priority=C.PRI_URGENT, urgent_reason="Cần số cho 12.12, họp BOD thứ Năm")
    mk("clean", HIEN, dt.date(2026, 11, 6), 15, title="Làm sạch file khách hàng", request_type="Xử lý dữ liệu",
       proposed_priority=C.PRI_LOW)
    mk("tiktok", HIEN, dt.date(2026, 11, 5), 11, title="Dashboard Affiliate partner TikTok")
    # Da huy
    mk("dup", DUYEN, dt.date(2026, 11, 4), title="Trùng yêu cầu rating")
    repo.at(dt.date(2026, 11, 4), 11)
    S.cancel(DUYEN, codes["dup"], "Trùng DR rating", repo=repo, pm=pm)
    repo.at(MON, 9, 30)
    return repo, pm, codes


# Dot 3 (quy tac co phien ban + duyet, chuyen phieu cu): phuong thuc repo gia nam o fake_d3.py.
from ecentric_workspace.data_hub.tests import fake_d3 as _fake_d3  # noqa: E402
_fake_d3.install(FakeRepo)
