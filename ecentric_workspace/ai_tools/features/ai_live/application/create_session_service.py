# Copyright (c) 2026, eCentric and contributors
"""18/11: tao phien live ngay tren /ai-live (ngan "+ Tao phien"). Phien = (may, ma live): 2 may cung co L1 la binh thuong,
cung 1 may thi cam trung. Ten phien (ERP) = {may}-{ma live}, khong doi may / ma live sau khi tao.
Phien moi luon o trang thai Nhap (published_source = "new"): app chua nhan cho toi khi Phat hanh."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application import _session_form as SF
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_form_rules as F


class CreateSessionService:
    def __init__(self, sessions=None, machines=None, kits=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.kits = kits or DS.kits()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, form):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        form, now = SF.parse(form), self.clock()
        code = F.text(form.get("machine"))
        if not code:
            F.fail("machine", C.SessMsg.NEED_MACHINE)
        m = self.machines.get(code)
        if not m:
            F.fail("machine", C.SessMsg.MACHINE_UNKNOWN % code)
        live = F.live_id(form.get("live_id"))
        dup = self.sessions.find(code, live)
        if dup:
            F.fail("live_id", C.SessMsg.LIVE_TAKEN % (code, live, dup.get("title") or dup["id"]))
        name = "%s-%s" % (code, live)
        if self.sessions.get(name):             # vd may "A-B" + live "C" va may "A" + live "B-C"
            F.fail("live_id", C.SessMsg.NAME_TAKEN % name)
        for k in ("platform", "brand"):         # bat buoc khi tao (sua thi chi kiem o co mat)
            form.setdefault(k, "")
        view = {"slots": F.slots(form.get("slots") or [], SF.today(now)), "machine": code, "obs_port": 0,
                "lc_open_before_min": None}
        view.update({k: "" for k in C.SESSION_DRAFT_FIELDS})
        SF.apply(view, form, m, self.kits.exists, self.sessions.list())
        vals = {k: view[k] for k in C.SESSION_DRAFT_FIELDS}
        vals.update({"machine": code, "live_id": live, "lc_open_before_min": view["lc_open_before_min"],
                     "enabled": 0 if str(form.get("enabled", 1)).strip() in ("0", "false", "False", "") else 1,
                     "auto_obs_start": 1, "obs_port": 0, "published_source": C.PubSource.NEW})
        draft = P.draft_of(view, {"_new": True})
        sid = self.sessions.create(vals, [], draft, user, now)
        return SF.result(self.sessions.get(sid))
