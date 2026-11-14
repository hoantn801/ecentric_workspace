# Copyright (c) 2026, eCentric and contributors
"""Repository gia trong bo nho - cung chu ky voi infrastructure/store.py. Dung cho test service
(khong can bench) va cho agent kiem thu viet them truong hop."""
import copy
import datetime
import hashlib

from ecentric_workspace.dao_tao import constants as C


class Duplicate(Exception):
    pass


def uhash(u):
    return hashlib.sha1((u or "").lower().encode()).hexdigest()[:12]


class FakeRepo:
    def __init__(self, now=datetime.datetime(2026, 11, 12, 9, 0)):
        self.clock = now
        self.ms = 1_800_000_000_000
        self.quizzes, self.sessions, self.players_, self.answers_ = {}, {}, {}, {}
        self.profiles, self.tickets, self.lessons_, self.progress = {}, {}, {}, {}
        self.topics_, self.votes, self.files, self.xlsx = {}, {}, {}, {}
        self.emps = {}
        self.realtime, self.errors, self.seq = [], [], 0
        self.cache, self.flags = {}, {}

    # ---------------------------------------------------------------- tien ich test --
    def tick(self, ms):
        self.ms += int(ms)
        self.clock += datetime.timedelta(milliseconds=int(ms))

    def _id(self, p):
        self.seq += 1
        return "%s-%04d" % (p, self.seq)

    def now(self):
        return self.clock

    def now_ms(self):
        return self.ms

    def cache_get(self, key):
        return self.cache.get(key) if hasattr(self, "cache") else None

    def cache_set(self, key, value, ttl):
        self.cache[key] = value

    def flag(self, name):
        return bool(self.flags.get(name))

    def secret(self):
        return "site-secret-test"

    def commit(self):
        pass

    def is_duplicate(self, e):
        return isinstance(e, Duplicate)

    def log_error(self, title):
        self.errors.append(title)

    def publish_room(self, session, version):
        self.realtime.append((session, version))

    # ------------------------------------------------------------------------ quiz --
    def get_quiz(self, name):
        return copy.deepcopy(self.quizzes.get(name))

    def list_quizzes(self, limit=200):
        return [{k: q[k] for k in ("name", "title", "status", "owner", "modified", "last_played", "template")}
                | {"n_questions": len(q["questions"])}
                for q in self.quizzes.values() if q["status"] != C.QUIZ_ARCHIVED]

    def insert_quiz(self, f):
        name = self._id("QZ")
        q = {"name": name, "title": "", "description": "", "status": C.QUIZ_DRAFT, "template": "",
             "owner": "host@x", "modified": str(self.clock), "last_played": "", "questions": [],
             "settings": {}, "prizes": None}
        q.update(copy.deepcopy(f))
        self.quizzes[name] = q
        return name

    def save_quiz(self, name, f):
        self.tick(1000)
        self.quizzes[name].update(copy.deepcopy(f))
        self.quizzes[name]["modified"] = str(self.clock)
        return self.quizzes[name]["modified"]

    def touch_quiz_played(self, name):
        self.quizzes[name]["last_played"] = str(self.clock)

    # ---------------------------------------------------------------------- ho so --
    def get_profile(self, user):
        return copy.deepcopy(self.profiles.get(user))

    def save_profile(self, user, nickname, avatar):
        self.profiles[user] = {"nickname": nickname, "avatar": dict(avatar)}

    # ---------------------------------------------------------------------- phong --
    def get_session(self, name, fresh=False):
        return copy.deepcopy(self.sessions.get(name))

    def session_by_code(self, code):
        for s in sorted(self.sessions.values(), key=lambda s: s["created"], reverse=True):
            if s["code"] == code and s["phase"] in C.LIVE_PHASES:
                return copy.deepcopy(s)
        return None

    def live_codes(self):
        return {s["code"] for s in self.sessions.values() if s["phase"] in C.LIVE_PHASES}

    def live_sessions(self, since):
        return [{"name": s["name"], "title": s["title"], "code": s["code"], "host": s["host"],
                 "phase": s["phase"], "created": s["created"]}
                for s in self.sessions.values() if s["phase"] in C.LIVE_PHASES]

    def recent_sessions(self, limit=30):
        return [{"name": s["name"], "title": s["title"], "code": s["code"], "host": s["host"],
                 "phase": s["phase"], "quiz": s["quiz"], "created": s["created"], "ended_at": s["ended_at"]}
                for s in self.sessions.values()]

    def insert_session(self, f):
        name = self._id("QS")
        self.sessions[name] = {"name": name, "quiz": f["quiz"], "title": f["title"], "code": f["code"],
                               "host": f["host"], "phase": f["phase"], "index": 0, "version": 1,
                               "opened_ms": 0, "deadline_ms": 0, "started_at": "", "ended_at": "",
                               "created": str(self.clock) + str(self.seq),
                               "questions": copy.deepcopy(f["questions"]), "settings": dict(f["settings"]),
                               "prizes": copy.deepcopy(f["prizes"]), "state": dict(f["state"]),
                               "results": None}
        return name

    def lock_session(self, name):
        return self.get_session(name)

    def update_session(self, name, values):
        s = self.sessions[name]
        for k, v in copy.deepcopy(values).items():
            s[k] = str(v) if k in ("started_at", "ended_at") else v
        s["version"] += 1
        return s["version"]

    # -------------------------------------------------------------------- nguoi choi --
    def _pk(self, session, user):
        return "%s|%s" % (session, uhash(user))

    def get_player(self, session, user):
        return copy.deepcopy(self.players_.get(self._pk(session, user)))

    def players(self, session, locking=False):
        return [copy.deepcopy(p) for p in self.players_.values() if p["session"] == session]

    def count_players(self, session):
        return sum(1 for p in self.players_.values() if p["session"] == session and not p["kicked"])

    def insert_player(self, f):
        k = self._pk(f["session"], f["user"])
        if k in self.players_:
            raise Duplicate(k)
        p = {"name": k, "score": 0, "correct_count": 0, "correct_ms": 0, "streak": 0, "best_streak": 0,
             "answered": 0, "first_rank": 0, "kicked": 0, "flags": [], "powers": {}, "device": ""}
        p.update(copy.deepcopy(f))
        p["joined_at"] = str(f.get("joined_at"))
        self.tick(1)
        self.players_[k] = p
        return k

    def update_player(self, session, user, values):
        self.players_[self._pk(session, user)].update(copy.deepcopy(values))

    def played(self, user, limit=20):
        out = []
        for p in self.players_.values():
            if p["user"] == user and not p["kicked"]:
                s = self.sessions[p["session"]]
                out.append({"session": s["name"], "score": p["score"], "nickname": p["nickname"],
                            "title": s["title"], "phase": s["phase"], "ended_at": s["ended_at"],
                            "creation": s["created"]})
        return out[:limit]

    # ----------------------------------------------------------------------- tra loi --
    def _ak(self, session, index, user):
        return "%s|%d|%s" % (session, int(index), uhash(user))

    def insert_answer(self, f):
        k = self._ak(f["session"], f["q_index"], f["user"])
        if k in self.answers_:
            raise Duplicate(k)
        self.answers_[k] = copy.deepcopy(f)
        return k

    def answers(self, session, index=None, locking=False):
        return [copy.deepcopy(a) for a in self.answers_.values()
                if a["session"] == session and (index is None or a["q_index"] == index)]

    def count_answers(self, session, index):
        return len(self.answers(session, index))

    def count_active_answers(self, session, index, locking=True):
        return sum(1 for a in self.answers(session, index)
                   if not (self.get_player(session, a["user"]) or {}).get("kicked"))

    def get_answer(self, session, index, user):
        return copy.deepcopy(self.answers_.get(self._ak(session, index, user)))

    def mark_answers_applied(self, session, index):
        for a in self.answers_.values():
            if a["session"] == session and a["q_index"] == index:
                a["applied"] = 1

    # ------------------------------------------------------------------------ nhan su --
    def employee(self, user):
        return dict(self.emps.get(user) or {"employee_name": user.split("@")[0].title(), "department": ""})

    def full_names(self, users):
        return {u: (self.emps.get(u) or {}).get("employee_name", u) for u in set(users or []) if u}

    # ---------------------------------------------------------------------------- ve --
    def ticket_exists(self, source, ref, user):
        return (source, ref, user) in self.tickets

    def tickets_in_week(self, user, ws):
        return sum(t["count"] for (s, r, u), t in self.tickets.items()
                   if u == user and t["week_start"] == ws and not t.get("revoked"))

    def insert_ticket(self, f):
        k = (f["source"], f["ref"], f["user"])
        if k in self.tickets:
            raise Duplicate(k)
        self.tickets[k] = dict(f, revoked=0, creation=str(self.clock))

    def tickets_of(self, user, limit=30):
        return [dict(t, week_start=str(t["week_start"])) for (s, r, u), t in self.tickets.items() if u == user]

    def revoke_ticket(self, source, ref, user, by):
        t = self.tickets.get((source, ref, user))
        if t:
            t["revoked"] = 1
            return True
        return False

    # ----------------------------------------------------------------------- bai hoc --
    def lessons(self, published_only=True, limit=300):
        rows = [copy.deepcopy(l) for l in self.lessons_.values()
                if not published_only or l["status"] == C.LESSON_PUBLISHED]
        for r in rows:
            r.pop("body", None)
        return sorted(rows, key=lambda r: r.get("week_start") or "", reverse=True)

    def get_lesson(self, name):
        return copy.deepcopy(self.lessons_.get(name))

    def insert_lesson(self, f):
        name = self._id("LS")
        self.lessons_[name] = dict({"name": name, "published_at": None, "video_url": "", "slide_url": ""},
                                   **copy.deepcopy(f))
        return name

    def save_lesson(self, name, f):
        self.lessons_[name].update(copy.deepcopy(f))

    def progress_of(self, user, names=None):
        return {k[0]: copy.deepcopy(v) for k, v in self.progress.items()
                if k[1] == user and (names is None or k[0] in names)}

    def progress_for_lesson(self, lesson):
        return [dict(v, user=k[1]) for k, v in self.progress.items() if k[0] == lesson]

    def upsert_progress(self, lesson, user, values):
        row = self.progress.setdefault((lesson, user), {"lesson": lesson, "user": user, "quiz_score": None})
        row.update({k: (str(v) if isinstance(v, datetime.datetime) else v) for k, v in values.items()})

    def lesson_stats(self):
        return {}

    # ---------------------------------------------------------------------- binh chon --
    def topics(self):
        return sorted([dict(t) for t in self.topics_.values()], key=lambda t: -t["votes"])

    def get_topic(self, name):
        t = self.topics_.get(name)
        return dict(t) if t else None

    def insert_topic(self, f):
        name = self._id("TP")
        self.topics_[name] = dict({"name": name, "lesson": None, "description": ""}, **f)
        return name

    def update_topic(self, name, values):
        self.topics_[name].update(values)

    def my_votes(self, user):
        return [t for (t, u) in self.votes if u == user]

    def add_vote(self, topic, user):
        if (topic, user) in self.votes:
            raise Duplicate(topic)
        self.votes[(topic, user)] = 1

    def remove_vote(self, topic, user):
        return self.votes.pop((topic, user), None) is not None

    def recount_votes(self, topic):
        n = sum(1 for (t, u) in self.votes if t == topic)
        self.topics_[topic]["votes"] = n
        return n

    def lock_user_votes(self, user):
        pass

    # ------------------------------------------------------------------- quay so tuan --
    def draw_name(self, ws):
        return "draw-%s" % str(ws)[:10]

    def get_draw(self, name):
        return copy.deepcopy(getattr(self, "draws", {}).get(name))

    def lock_draw(self, name):
        return self.get_draw(name)

    def insert_draw(self, f):
        self.draws = getattr(self, "draws", {})
        name = self.draw_name(f["week_start"])
        if name in self.draws:
            raise Duplicate(name)
        self.draws[name] = {"name": name, "title": f["title"], "week_start": str(f["week_start"]),
                            "draw_at": f["draw_at"], "range": f["range"], "status": f["status"],
                            "prizes": copy.deepcopy(f["prizes"]), "results": None, "drawn_at": ""}
        return name

    def update_draw(self, name, values):
        self.draws[name].update(copy.deepcopy(values))

    def due_draws(self, now):
        return [n for n, d in getattr(self, "draws", {}).items() if d["status"] == "Open" and d["draw_at"] <= now]

    def week_tickets(self, ws):
        out = {}
        for (s, r, u), t in self.tickets.items():
            if str(t["week_start"]) == str(ws) and not t.get("revoked") and t["count"] > 0:
                out[u] = out.get(u, 0) + t["count"]
        return out

    def draw_numbers(self, draw, user=None, locking=False):
        self.dnums = getattr(self, "dnums", {})
        return sorted([dict(v) for (d, u, s), v in self.dnums.items() if d == draw and (user is None or u == user)],
                      key=lambda r: r["number"])

    def insert_draw_number(self, draw, user, slot, number, auto=0):
        self.dnums = getattr(self, "dnums", {})
        if (draw, user, slot) in self.dnums:
            raise Duplicate(slot)
        self.dnums[(draw, user, slot)] = {"user": user, "slot": slot, "number": number, "auto": auto}

    def delete_draw_number(self, draw, user, slot):
        getattr(self, "dnums", {}).pop((draw, user, slot), None)

    def notify(self, user, title, message, url, ref, dedupe_key, reference_doctype=None):
        self.notified = getattr(self, "notified", [])
        self.notified.append((user, title))

    def rollback(self):
        pass

    # ---------------------------------------------------------------------------- tep --
    def file_owner(self, url):
        return self.files.get(url)

    def read_xlsx_rows(self, url):
        return self.xlsx[url]
