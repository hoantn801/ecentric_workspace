# Copyright (c) 2026, eCentric and contributors
"""Cap nhat trang thai trao giai (1 hoac nhieu nguoi thang) tu trang ERP. Ghi chu tuy chon (None = giu nguyen).
App gui lai ket qua sau do: giu thay doi cua ERP tru khi tren app cung doi lai (xem race_rules.merge_winners)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR


class SetPrizeStatusService:
    def __init__(self, races=None, atomic=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.races = races or DS.races()
        self.atomic = atomic or (lambda fn: fn())

    def execute(self, roles, items, status, note=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        label = RR.prize_label(status)
        if not label:
            raise C.AiLiveError(C.RaceMsg.BAD_STATUS)
        raw = _common.parse_json(items, "danh sách người thắng") if isinstance(items, str) else items
        pairs = []
        for it in raw if isinstance(raw, list) else []:
            rid, rank = str((it or {}).get("race") or ""), (it or {}).get("rank")
            if C.RACE_ID_RE.match(rid) and str(rank).isdigit() and int(rank) >= 1:
                pairs.append((rid, int(rank)))
        if not pairs:
            raise C.AiLiveError(C.RaceMsg.NO_ITEMS)
        if len(pairs) > C.RACE_BULK_MAX:
            raise C.AiLiveError(C.RaceMsg.TOO_MANY % C.RACE_BULK_MAX)
        note = None if note is None else str(note).strip()[:C.MAX_RACE_NOTE]
        n = self.atomic(lambda: self.races.set_prize_status(pairs, label, note))
        return {"updated": n, "status": label}
