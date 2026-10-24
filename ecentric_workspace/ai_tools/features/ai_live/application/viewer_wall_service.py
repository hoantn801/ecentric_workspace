# Copyright (c) 2026, eCentric and contributors
"""Man "Xem nhu khach": moi phien dang trong gio live / dang len song -> 1 o anh phia khach.
Nguon anh theo thu tu: xem truoc Seller Center / LIVE Manager (extension) > khung hinh luong cong khai TikTok >
dien thoai (phone box). Anh qua VIEWER_STALE_S -> o xam "mat hinh".
fix10h: moi o kem tinh trang giong man Truc live (mat lien lac / KHAN / canh bao + moc "da X phut") va bo dem tren dau."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application._session_view import health_index, summarize
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import wall_rules as WR

ON_AIR = (C.SessionStatus.ON_AIR, C.SessionStatus.PROBLEM)


def pick_source(row, now):
    """(kind, ts) cua anh phia khach moi nhat theo thu tu uu tien; anh cu > stale van tra (de hien xam)."""
    best = None
    for kind in C.VIEWER_SOURCES:
        t = float((row or {}).get(kind + "_thumb_ts") or 0)
        if t and now - t <= C.VIEWER_STALE_S:
            return kind, t
        if t and (best is None or t > best[1]):
            best = (kind, t)
    return best or (None, 0)


class ViewerWallService:
    def __init__(self, sessions=None, health=None, settings=None, clock=None, machines=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as DM
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.health = health or DM.health()
        self.settings = settings or DM.settings()
        self.clock = clock or R.now_ts
        self.machines = machines or DM.machines()

    def execute(self, roles):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now, cfg = self.clock(), self.settings.get()
        hi = health_index(self.health.all())
        lost_codes = {m["machine_code"] for m in self.machines.heartbeats() if WR.machine_lost(m, now, cfg)}
        tiles = []
        for s in self.sessions.list():
            row = hi.get(R.key_of(s["machine"], s["id"])) if s["machine"] else None
            sm = summarize(s, row, now, cfg)
            if sm["status"] not in ON_AIR:
                continue
            kind, ts = pick_source(row, now)
            tiles.append({"id": s["id"], "title": s["title"], "brand": s["brand"], "platform": s["platform"],
                          "key": sm["key"], "status": sm["status"], "watch_url": s.get("watch_url") or "",
                          "source": kind, "source_ts": ts, "age_s": int(now - ts) if ts else None,
                          "stale": not ts or now - ts > C.VIEWER_STALE_S, "viewers": sm["viewers"],
                          "wall": self._wall(row, s["machine"] in lost_codes, now, cfg)})
        tiles.sort(key=lambda t: (t["brand"], t["title"]))
        counts = {k: sum(1 for t in tiles if t["wall"]["level"] == k) for k in ("lost", "crit", "warn", "ok")}
        return {"tiles": tiles, "server_time": now, "refresh_s": 5, "stale_s": C.VIEWER_STALE_S, "counts": counts}

    @staticmethod
    def _wall(row, machine_lost, now, cfg):
        """Muc giong the Truc live: lost / crit / warn / ok + van de + moc thoi gian."""
        if not row:
            return {"level": "lost", "text": "Chưa có tín hiệu từ máy", "since_ts": 0}
        ev = R.evaluate(row, now, cfg)
        level = WR.card_level(ev["level"], machine_lost and ev["expected"])
        p = WR.problem_of(level, ev, row, now) or {}
        return {"level": level, "text": p.get("text") or "", "since_ts": p.get("since_ts") or 0}
