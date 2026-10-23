# Copyright (c) 2026, eCentric and contributors
"""Man Truc live (wallboard, B2 - fix10h): 1 endpoint tong hop poll 15 s. Tra: bo dem (Dang live / KHAN / Canh bao /
Mat lien lac / Lo gio hom nay), dai may mat lien lac, the tung live (van de to nhat + "da X phut", anh, len song bao
lau, fps, che do phat, AI chinh / du phong, chi phi hom nay so voi tran brand, lenh gan day, su co dang mo), live
"cho gio" trong 6 gio toi, may ranh. Anh tai rieng (monitor_thumb), chi khi doi."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import incident_rules as I
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
from ecentric_workspace.ai_tools.features.ai_live.domain import wall_rules as WR


class WallboardService:
    def __init__(self, health=None, machines=None, sessions=None, settings=None, incidents=None, commands=None,
                 costs=None, brands=None, actuals=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.health = health or D.health()
        self.machines = machines or D.machines()
        self.sessions = sessions or DS.sessions()
        self.settings = settings or D.settings()
        self.incidents = incidents or D.incidents()
        self.commands = commands or DS.commands()
        self.costs = costs or D.costs()
        self.brands = brands or D.brands()
        self.clock = clock or R.now_ts
        self._actuals = actuals

    def actuals(self):
        if self._actuals is None:
            from ecentric_workspace.ai_tools.features.ai_live.application.schedule_actuals_service import ScheduleActualsService
            self._actuals = ScheduleActualsService(sessions=self.sessions)
        return self._actuals

    def execute(self, roles, brand=None, machine=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now, cfg = self.clock(), self.settings.get()
        today = datetime.fromtimestamp(now, R._VN).date()
        hb = {m["machine_code"]: m for m in self.machines.heartbeats()}
        sessions = self.sessions.list()
        sess = {s["id"]: s for s in sessions}
        rows = self.health.all()
        incs = self.incidents.open_all()
        silent = {i["machine"]: i for i in incs if i["kind"] == C.IncKind.SILENT}
        fwd = {}
        for i in incs:
            if i["kind"] == C.IncKind.FORWARD:
                fwd.setdefault((i["machine"], i["live"]), []).append(i)
        cmds = {}
        for c in self.commands.since(now - C.WALL_CMD_WINDOW_S):
            cmds.setdefault((c["machine"], c["live"]), []).append(c)
        act = self.actuals().compute(today, now)
        failover = {}
        for r in act["rows"]:
            if r["report"]:
                failover[r["live"]] = max(failover.get(r["live"], 0), int(r["report"].get("ai_failover_count") or 0))
        lost_codes = {c for c, m in hb.items() if WR.machine_lost(m, now, cfg)}
        lost_machines = [self._lost(hb[c], sessions, rows, silent.get(c), now, sess) for c in sorted(lost_codes)]
        lost_machines = [x for x in lost_machines if x["lives"] or x["incident"]]
        costs, cards, carded = {}, [], set()
        for row in rows:
            ev = R.evaluate(row, now, cfg)
            lost = row.get("machine") in lost_codes and ev["expected"]
            if ev["level"] == C.Level.IDLE and not lost:
                continue
            m = hb.get(row.get("machine")) or {}
            cards.append(self._card(row, ev, m, sess.get(row["live"]), lost, now, costs, failover, fwd, cmds))
            carded.add(row["live"])
        waiting = self._waiting(sessions, carded, now)
        busy = {c["machine"] for c in cards} | {w["machine"] for w in waiting} | lost_codes
        idle = sorted(c for c, m in hb.items() if c not in busy and (W.silent_s(m, now) or 0) <= cfg["dead_man_min"] * 60)
        brands = sorted({c["brand"] for c in cards if c["brand"]} | {w["brand"] for w in waiting if w["brand"]})
        machines = sorted(set(hb) | {c["machine"] for c in cards})
        if brand:
            cards = [c for c in cards if c["brand"] == brand]
            waiting = [w for w in waiting if w["brand"] == brand]
            lost_machines = [x for x in lost_machines if brand in x["brands"]]
        if machine:
            cards = [c for c in cards if c["machine"] == machine]
            waiting = [w for w in waiting if w["machine"] == machine]
            lost_machines = [x for x in lost_machines if x["machine"] == machine]
            idle = [c for c in idle if c == machine]
        airing = {c["live"] for c in cards if c["on_air"] and c["level"] != "lost"}
        # "Lo gio hom nay" = app bao lo + khung qua 15 phut khong bao cao ma live cung khong dang len song (app cu chua gui bao cao)
        missed = WR.missed_today(act["rows"], airing, hb, brand, machine)
        trows = [r for r in act["rows"] if (not brand or r.get("brand") == brand) and (not machine or r.get("machine") == machine)]
        minfo = [WR.machine_view(hb[c], now, cfg, cards) for c in sorted(hb) if not machine or c == machine]
        return {"server_time": now, "refresh_s": C.WALL_REFRESH_S, "counters": WR.counters(cards, lost_machines, missed),
                "today": WR.today_rows(trows, cards, now), "machine_info": minfo, "date": today.isoformat(),
                "lost_machines": lost_machines, "cards": WR.sort_cards(cards), "waiting": waiting, "idle_machines": idle,
                "brands": brands, "machines": machines, "actions": list(C.WALL_ACTIONS),
                "inc_open": sum(1 for i in incs if i["status"] == C.IncStatus.OPEN)}

    def _lost(self, m, sessions, rows, inc, now, by_id):
        lives = W.expected_lives(m, [s for s in sessions if s.get("enabled")], rows, now)
        for x in lives:
            x["name"] = (by_id.get(x["live"]) or {}).get("title") or x["name"]
        crit = [a[:-5].strip() for a in m.get("hb_alerts") or [] if a.endswith("(đỏ)")][:2]
        return {"machine": m["machine_code"], "label": m.get("label") or "", "since_ts": float(m["hb_last_seen_ts"]),
                "lives": [("%s – %s" % (x["brand"], x["name"])) if x.get("brand") else x["name"] for x in lives],
                "brands": sorted({x["brand"] for x in lives if x.get("brand")}), "last_problems": crit,
                "incident": I.view(inc, now) if inc else None}

    def _card(self, row, ev, m, s, lost, now, costs, failover, fwd, cmds):
        level = WR.card_level(ev["level"], lost)
        air = next((x for x in m.get("hb_lives") or [] if x.get("live") == row["live"]), None)
        brand = row.get("brand") or (s or {}).get("brand") or ""
        if brand not in costs:
            cap = float((self.brands.get(brand) or {}).get("daily_cost_cap_usd") or 0) if brand else 0
            costs[brand] = WR.cost_view(self.costs.day_total(brand, datetime.fromtimestamp(now, R._VN).date().isoformat())
                                        if brand else 0, cap)
        metrics = row.get("metrics") or {}
        incs = sorted(fwd.get((row.get("machine"), row["live"]), []), key=lambda i: i["level"] != C.Level.CRIT)
        thumb_kind = next((k for k in ("obs", "platform", "phone") if row.get(k + "_thumb_ts")), "")
        return {"key": row["key"], "machine": row.get("machine") or "", "live": row["live"],
                "title": (s or {}).get("title") or row["live"], "brand": brand, "level": level,
                "problem": WR.problem_of(level, ev, row, now),
                "reasons": [{"level": r["level"], "text": r["text"]} for r in ev.get("reasons", [])[1:3]],
                "state": row.get("state") or "", "on_air": bool(air) or row.get("state") in C.ON_AIR_STATES,
                "on_air_since_ts": float((air or {}).get("since") or 0), "mode": WR.MODE_TEXT.get((air or {}).get("mode"), ""),
                "fps": metrics.get("fps"), "gpu": metrics.get("gpu"),
                "obs_port": int(P.served_view(s, now).get("obs_port") or 0) if s else 0, "ai": WR.ai_text(row.get("extra"), failover.get(row["live"], 0)),
                "cost": costs[brand], "minimal": bool(m.get("hb_minimal")), "last_seen_ts": float(row.get("last_seen_ts") or 0),
                "thumb": {"kind": thumb_kind, "ts": float(row.get(thumb_kind + "_thumb_ts") or 0) if thumb_kind else 0},
                "erp": bool(s), "faq_n": len((row.get("extra") or {}).get("faq") or []),
                "commands": [{"id": c["id"], "action": c["action"], "status": c["status"], "result": c["result"],
                              "ts": c["created_ts"]} for c in (cmds.get((row.get("machine"), row["live"])) or [])[:3]],
                "incident": I.view(incs[0], now) if incs else None}

    @staticmethod
    def _waiting(sessions, carded, now):
        out = []
        for s in sessions:
            if not s.get("enabled") or s["id"] in carded:
                continue
            v = P.served_view(s, now)
            if not v.get("machine"):
                continue
            w = S.next_window(v["slots"], now, 2)
            if w and now < w[0] <= now + C.WALL_WAIT_AHEAD_S:
                out.append({"live": s["id"], "title": s.get("title") or s["id"], "brand": s.get("brand") or "",
                            "machine": v["machine"], "start_ts": w[0], "end_ts": w[1]})
        return sorted(out, key=lambda x: x["start_ts"])
