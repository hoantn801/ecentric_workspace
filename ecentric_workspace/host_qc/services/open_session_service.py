# Copyright (c) 2026, eCentric and contributors
"""session_open: phien -> Running. Phien chua co tren ERP (app QC ngoai lich) -> tao phien source=unplanned
tu cau hinh app gui kem, gan cho chinh may nay. Gui lai nhieu lan (hang doi cua app) cho cung ket qua."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import SESSION_ID_RE
from ecentric_workspace.host_qc.constants.statuses import SessionSource, SessionStatus
from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.utils.time import now, to_dt


def _join(v):
    """Danh sach (dang app gui) hoac chuoi -> moi dong 1 muc."""
    if isinstance(v, (list, tuple)):
        return "\n".join(str(x).strip() for x in v if str(x).strip())[:2000]
    return str(v or "")[:2000]


class OpenSessionService:
    def __init__(self, sessions=None, machines=None, clock=now):
        self.sessions = sessions or SessionRepository()
        self.machines = machines or MachineRepository()
        self.clock = clock

    def execute(self, machine, payload):
        sid = str(payload.get("session_id") or "").strip()
        if not SESSION_ID_RE.match(sid):
            raise InvalidInput(M.BAD_SESSION_ID)
        started = to_dt(payload.get("started_at")) or self.clock()
        s = self.sessions.get_brief(sid)
        if not s:
            cfg = payload.get("config")
            if not isinstance(cfg, dict):
                raise NotFoundError(M.SESSION_CONFIG_MISSING % sid)
            self.sessions.create(self.from_config(sid, cfg, machine["name"], started), from_machine=True)
            s = self.sessions.get_brief(sid)
        elif s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        if s["status"] != SessionStatus.CLOSED.value:
            vals = {"status": SessionStatus.RUNNING.value, "config_hash": str(payload.get("config_hash") or "")[:80],
                    "app_version": str(payload.get("app_version") or "")[:40]}
            if not s.get("started_at"):
                vals["started_at"] = started
            self.sessions.update(sid, vals)
            self.machines.set_current_session(machine["name"], sid)
        return {"name": sid}

    @staticmethod
    def from_config(sid, c, machine_name, started):
        def rng(rows):
            return [{"from_time": to_dt(r.get("from")), "to_time": to_dt(r.get("to")), "note": str(r.get("note") or "")[:140]}
                    for r in rows or [] if isinstance(r, dict) and to_dt(r.get("from")) and to_dt(r.get("to"))]
        banned = c.get("banned") if isinstance(c.get("banned"), dict) else {}
        return {
            "session_id": sid, "title": str(c.get("title") or sid)[:140], "machine": machine_name,
            "status": SessionStatus.RUNNING.value, "source": SessionSource.UNPLANNED.value,
            "platform": c.get("platform") if c.get("platform") in ("tiktok", "shopee") else "tiktok",
            "tiktok_username": str(c.get("tiktok_username") or "")[:140],
            "format": c.get("format") if c.get("format") in ("sales", "mega", "kol", "branding", "education") else "sales",
            "push_sale": c.get("push_sale") if c.get("push_sale") in ("high", "medium", "low", "none") else "medium",
            "planned_start": started, "planned_end": started, "started_at": started,
            "hosts": [{"host_id": str(h.get("host_id") or "")[:20], "host_name": str(h.get("name") or h.get("host_id") or "")[:140],
                       "role": h.get("role") if h.get("role") in ("main", "support", "kol", "guest") else "main",
                       "mic_device": str(h.get("mic_device") or "")[:140], "on_camera": 1 if h.get("on_camera") else 0}
                      for h in c.get("hosts") or [] if isinstance(h, dict) and h.get("host_id")],
            "products": [{"code": str(p.get("code") or "")[:40], "product_name": str(p.get("name") or "")[:140],
                          "aliases": _join(p.get("aliases")), "pronunciation": str(p.get("pronunciation") or "")[:140],
                          "usp": _join(p.get("usp")), "target": str(p.get("target") or "")[:140],
                          "price": str(p.get("price") or "")[:140], "deal": str(p.get("deal") or "")[:140]}
                         for p in c.get("products") or [] if isinstance(p, dict) and p.get("code")],
            "deals": [{"deal_id": str(x.get("id") or "")[:40], "text": str(x.get("text") or "")[:140],
                       "keywords": _join(x.get("keywords")), "important": 1 if x.get("important") else 0,
                       "valid_from": to_dt(x.get("from")), "valid_to": to_dt(x.get("to"))}
                      for x in c.get("deals") or [] if isinstance(x, dict) and x.get("id")],
            "banned_phrases": [{"kind": k, "phrase": str(p)[:140]} for k in ("commitment", "offensive")
                               for p in banned.get(k) or [] if str(p).strip()],
            "scripted_silences": rng(c.get("scripted_silences")),
            "scripted_breaks": rng(c.get("scripted_breaks")),
        }
