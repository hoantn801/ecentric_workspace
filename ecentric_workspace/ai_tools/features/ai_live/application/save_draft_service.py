# Copyright (c) 2026, eCentric and contributors
"""fix10g: sua lich tren ERP -> chi vao BAN NHAP cua phien. App chi nhan khi phat hanh.
18/11: them mo tab truoc gio live; tao / sua phien tren /ai-live -> ca ten / brand / san / username / shop / bo live /
che do / link xem / dien thoai cung vao nhap (`fields`). May KHONG doi duoc sau khi tao (PO chot 18/11).
Kiem som: khung hop le, khong trung trong phien, brand da giao cho may. Suc chua may kiem khi phat hanh.
Nhap giong het ban dang phat hanh -> tu xoa nhap (phien chua phat hanh lan nao: luon giu nhap day du)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application import _session_form as SF
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_form_rules as F


class SaveDraftService:
    def __init__(self, sessions=None, machines=None, clock=None, kits=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.kits = kits or DS.kits()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, name, slots=None, machine=None, obs_port=None, lc_open_before_min=None, fields=None):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        sess = self.sessions.get(str(name or ""))
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        now = self.clock()
        view = P.draft_view(sess)
        if slots is not None:
            raw = _common.parse_json(slots, "khung giờ") if isinstance(slots, str) else slots
            view["slots"] = F.slots(raw if raw is not None else [], SF.today(now))
        code = F.text(machine)
        if code and code != (sess["machine"] or ""):
            F.fail("machine", C.SessMsg.MACHINE_LOCKED)
        if obs_port is not None:
            port = int(obs_port or 0)
            if port and not (C.OBS_PORT_RANGE[0] <= port <= C.OBS_PORT_RANGE[1]):
                raise C.AiLiveError(C.SessMsg.BAD_PORT)
            view["obs_port"] = port
        if lc_open_before_min is not None:      # "" = xoa (theo cai dat tren app)
            view["lc_open_before_min"] = F.open_before(lc_open_before_min)
        form = SF.parse(fields)
        if form:
            for k in ("machine", "live_id"):
                if k in form and F.text(form[k]) and F.text(form[k]) != F.text(sess["machine"] if k == "machine" else sess["live"]):
                    F.fail(k, C.SessMsg.MACHINE_LOCKED if k == "machine" else C.SessMsg.LIVE_LOCKED)
            SF.apply(view, form, self.machines.get(view["machine"]) if "brand" in form else None,
                     self.kits.exists, self.sessions.list(), sess["id"])
        if P.is_new(sess) and form:                # 18/11: phien chua phat hanh - ban ghi theo nhap (danh sach hien ngay)
            self.sessions.mirror_unpublished(sess["id"], {k: view[k] for k in C.SESSION_DRAFT_FIELDS})
            sess = self.sessions.get(sess["id"])
        pub = P.published_view(sess)
        if P.same(view, pub):
            self.sessions.save_draft(sess["id"], None, 0, user, now)
        else:
            draft = P.draft_of(view, pub)
            base = sess["draft_base_version"] if sess.get("draft") else sess.get("published_version") or 0
            self.sessions.save_draft(sess["id"], draft, base, user, now)
        return SF.result(self.sessions.get(sess["id"]))
