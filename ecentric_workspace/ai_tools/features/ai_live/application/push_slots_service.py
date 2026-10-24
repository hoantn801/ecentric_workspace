# Copyright (c) 2026, eCentric and contributors
"""App tren may phat gui lai toan bo khung gio cua 1 phien live cua chinh may do (lich 2 chieu: ERP phat hanh qua
man Dong bo, app keo qua get_config.lives[].schedule). Ma live tren app = ma phien tren ERP (get_config.lives[].id).

fix10g: ERP NHAN LUON thanh 1 ban phat hanh moi (nguon "app"), khong qua ban nhap va khong giu gio cu (app da tu ap).
- App gui `base_version` (= lives[].schedule_version luc tai) ma ERP da phat hanh ban moi hon cho phien nay va khac
  -> tu choi, app tai lai lich roi sua lai (khong de app ghi de thay doi ERP ma no chua thay).
  Khong gui base_version (app cu) -> "sua sau cung thang".
- Phien dang giu gio cu (lich moi da phat hanh, app dang chay ban cu) -> tu choi toi het lan do (ma schedule_held).
  Luc giu, get_config tra schedule_version = ban CU dang chay (24/10), nen het moc giu ma app gui base cu -> schedule_stale.
- Ai dang co ban nhap cho phien nay -> ban nhap thanh "lech" (draft_state stale), phai chon giu / bo truoc khi phat hanh.
- Van kiem trung gio, suc chua may (tinh ca lan dang giu gio cu), cong OBS."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class PushSlotsService:
    def __init__(self, machines=None, sessions=None, publisher=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or DS.machines_all()
        self.sessions = sessions or DS.sessions()
        self._publisher = publisher
        self.clock = clock or R.now_ts

    def execute(self, user, machine, live, slots, base_version=None):
        m = _common.require_machine(self.machines, user, machine)
        sess = self._session_of(m, str(live or "").strip())
        raw = _common.parse_json(slots, "khung giờ") if isinstance(slots, str) else slots
        if not isinstance(raw, list):
            raise C.AiLiveError(C.SessMsg.BAD_SLOTS)          # khong tu xoa lich khi app gui thieu slots
        clean = S.norm_slots(raw)
        before = P.published_view(sess)
        after = dict(before, slots=clean)
        version = sess.get("published_version") or 0
        if not P.same(before, after):
            held = float(sess.get("held_until_ts") or 0)
            if held > self.clock() and sess.get("prev"):   # app dang chay ban cu - sua luc nay se de mat lich moi
                # kiem TRUOC base_version: luc giu gio, get_config tra version cua ban cu -> neu bao "stale" thi app
                # tai lai van nhan ban cu, lap vo han
                raise C.AiLiveError(C.PubMsg.APP_HELD % (sess["title"], datetime.fromtimestamp(held, R._VN).strftime("%H:%M")),
                                    C.ErrCode.SCHEDULE_HELD, {"held_until": held, "schedule_version": version})
            raw_base = "" if base_version is None else str(base_version).strip()
            base = int(raw_base) if raw_base.lstrip("-").isdigit() else None
            if base is not None and base < version:
                raise C.AiLiveError(C.PubMsg.APP_STALE % (sess["title"], version), C.ErrCode.SCHEDULE_STALE,
                                    {"schedule_version": version, "base_version": base})
            pub = self.publisher()
            all_s = self.sessions.list()
            _, errors = pub.plan(all_s, {sess["id"]: after}, no_hold=True)
            if errors:
                raise C.AiLiveError(errors[0]["error"])
            version = pub.write(user, all_s, {sess["id"]: after}, {}, C.PubSource.APP, refresh=False)["version"]
        return {"session": self.sessions.get(sess["id"]), "slots": clean, "schedule": S.to_app_schedule(clean),
                "schedule_version": version}

    def publisher(self):
        if self._publisher is None:
            from ecentric_workspace.ai_tools.features.ai_live.application.publish_schedule_service import PublishScheduleService
            self._publisher = PublishScheduleService(sessions=self.sessions, machines=self.machines)
        return self._publisher

    def _session_of(self, m, live):
        if not C.LIVE_RE.match(live):
            raise C.AiLiveError(C.SessMsg.BAD_ID)
        sess = next((s for s in self.sessions.by_machine(m["machine_code"]) if s["id"] == live), None)
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_ON_MACHINE % (live, m["machine_code"]))
        if sess["brand"] and sess["brand"] not in _common.machine_brands(m):
            raise C.AiLiveError(C.SessMsg.BRAND_OFF % (sess["brand"], m["machine_code"]))
        return sess
