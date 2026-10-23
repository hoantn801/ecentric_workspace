# Copyright (c) 2026, eCentric and contributors
"""Luat Lich live ban nhap -> phat hanh (fix10g, thuan Python, khong goi DB).

"View" cua 1 phien = {slots, machine, obs_port}: ban da phat hanh (app dang/ se nhan), ban nhap (chua phat hanh)
hoac ban cu (prev, con giu cho lan dang live). Cac ca chong xung dot:
- dang live luc phat hanh: giu gio bat dau / may / kenh cua lan do toi het lan do (chi keo dai gio ket thuc thi ap ngay);
- sap len song trong LOCK_MIN phut: giu gio cu cho lan do, tru khi phat hanh khan;
- may nhan lich moi sau khi da len live theo gio cu (nhan muon): giu gio cu toi het lan do (giu "muon", ghi lai).
App giu nguyen live dang chay khi ERP doi gio (src/schedule: dang trong gio cu thi "de yen"), nen ERP chi can
khong gui lich gay doi khoa lan dien ra (slotId@gio bat dau) giua chung."""
from datetime import datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S

_VN = S._VN
_WD = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}


def published_view(sess):
    return {"slots": list(sess.get("slots") or []), "machine": sess.get("machine") or "",
            "obs_port": int(sess.get("obs_port") or 0)}


def draft_view(sess):
    """Ban nhap ghep len ban da phat hanh (truong nao nhap khong co thi giu ban phat hanh)."""
    v, d = published_view(sess), sess.get("draft") or {}
    for k in ("slots", "machine", "obs_port"):
        if k in d:
            v[k] = d[k] if k != "obs_port" else int(d[k] or 0)
    return v


def same(a, b):
    return a["machine"] == b["machine"] and int(a["obs_port"] or 0) == int(b["obs_port"] or 0) and \
        [_key(s) for s in a["slots"]] == [_key(s) for s in b["slots"]]


def _key(s):
    return (tuple(s.get("days") or []), s.get("date") or None, s["start"], s["end"])


def draft_state(sess):
    if not sess.get("draft"):
        return C.DraftState.NONE
    if int(sess.get("published_version") or 0) > int(sess.get("draft_base_version") or 0):
        return C.DraftState.STALE
    return C.DraftState.READY


def _days_txt(s):
    if s.get("date"):
        return "chỉ " + "/".join(reversed(s["date"].split("-")[1:]))
    d = s.get("days") or list(range(1, 8))
    if d == list(range(1, 8)):
        return "mỗi ngày"
    if len(d) > 2 and d == list(range(d[0], d[-1] + 1)):
        return "%s–%s" % (_WD[d[0]], _WD[d[-1]])
    return ", ".join(_WD[x] for x in d)


def slot_text(s):
    return "%s %s–%s" % (_days_txt(s), s["start"], s["end"])


def diff_texts(before, after):
    """Cac dong mo ta thay doi cho nguoi doc (toi da MAX_DIFF_LINES)."""
    out = []
    if before["machine"] != after["machine"]:
        out.append("Chuyển máy %s → %s" % (before["machine"] or "chưa gán", after["machine"] or "chưa gán"))
    if int(before["obs_port"] or 0) != int(after["obs_port"] or 0):
        out.append("Đổi kênh OBS %s → %s" % (before["obs_port"] or "–", after["obs_port"] or "–"))
    b_keys, a_keys = [_key(s) for s in before["slots"]], [_key(s) for s in after["slots"]]
    gone = [s for s, k in zip(before["slots"], b_keys) if k not in a_keys]
    new = [s for s, k in zip(after["slots"], a_keys) if k not in b_keys]
    for o in list(gone):                        # cung ngay/thu, doi gio -> 1 dong "a → b"
        n = next((x for x in new if (x.get("date"), x.get("days")) == (o.get("date"), o.get("days"))), None)
        if n:
            out.append("%s: %s–%s → %s–%s" % (_days_txt(o), o["start"], o["end"], n["start"], n["end"]))
            gone.remove(o)
            new.remove(n)
    out += ["Thêm khung " + slot_text(s) for s in new] + ["Bỏ khung " + slot_text(s) for s in gone]
    return out[:C.MAX_DIFF_LINES]


def _around(ts, back=1, ahead=1):
    d = datetime.fromtimestamp(ts, _VN).date()
    return [d + timedelta(days=k) for k in range(-back, ahead + 1)]


def occurrence_at(slots, ts):
    """Lan dien ra dang chay luc ts: (start, end, slot_index) hoac None."""
    return next(((a, b, i) for a, b, i in S.occurrences(slots, _around(ts)) if a <= ts < b), None)


def next_occurrence(slots, ts):
    return next(((a, b, i) for a, b, i in S.occurrences(slots, _around(ts, 1, 2)) if a > ts), None)


def preserved(occ, before, after):
    """Lan dien ra `occ` (theo ban cu) van y nguyen voi app trong ban moi: cung may, kenh, cung vi tri khung (app dat
    ma khung theo thu tu: erp1, erp2...), cung ngay va gio bat dau, gio ket thuc bang hoac muon hon (keo dai thi app
    theo duoc ngay; rut ngan thi app van chay toi gio cu nen phai giu)."""
    a, b, i = occ
    if before["machine"] != after["machine"] or int(before["obs_port"] or 0) != int(after["obs_port"] or 0):
        return False
    if i >= len(after["slots"]):
        return False
    x, y = before["slots"][i], after["slots"][i]
    if (x.get("date"), list(x.get("days") or []), x["start"]) != (y.get("date"), list(y.get("days") or []), y["start"]):
        return False
    new = next((o for o in S.occurrences(after["slots"], _around(a)) if o[0] == a and o[2] == i), None)
    return bool(new) and new[1] >= b


def hold_for_publish(before, after, now, lock_s, urgent=False):
    """(giu_toi_ts, ly_do) khi phat hanh `after` thay `before` luc `now`; (0, "") = ap dung ngay."""
    if not before["machine"] or not before["slots"]:
        return 0, ""
    occ = occurrence_at(before["slots"], now)
    if occ:
        return (0, "") if preserved(occ, before, after) else (occ[1], C.HoldWhy.ON_AIR)
    nxt = next_occurrence(before["slots"], now)
    if urgent or not nxt or nxt[0] - now > lock_s or preserved(nxt, before, after):
        return 0, ""
    return nxt[1], C.HoldWhy.SOON


def late_hold(sess, prev_machine_fetch_ts, now):
    """May cu chua tai lich tu luc phat hanh ma lan dien ra theo ban cu da bat dau -> giu toi het lan do.
    Tra end_ts hoac 0."""
    prev, pub_ts = sess.get("prev"), float(sess.get("published_ts") or 0)
    if not prev or not pub_ts or float(sess.get("held_until_ts") or 0) or prev_machine_fetch_ts >= pub_ts:
        return 0
    if not prev.get("machine"):
        return 0
    occ = occurrence_at(prev["slots"], now)
    if not occ:
        return 0
    return 0 if preserved(occ, prev, published_view(sess)) else occ[1]


def served_view(sess, now):
    """Ban app nhan luc now: ban cu neu dang giu, khong thi ban da phat hanh. Them held_until (0 = khong giu)."""
    until = float(sess.get("held_until_ts") or 0)
    if sess.get("prev") and until > now:
        return dict(sess["prev"], held_until=until)
    return dict(published_view(sess), held_until=0)


def held_slot(prev, until):
    """Lan dien ra dang giu (ban cu) -> 1 khung 'chi ngay' de tinh suc chua may khi phat hanh."""
    occ = occurrence_at(prev["slots"], until - 1)
    if not occ:
        return None
    a, b, _ = occ
    da, db = datetime.fromtimestamp(a, _VN), datetime.fromtimestamp(b, _VN)
    return {"days": [], "date": da.date().isoformat(), "start": da.strftime("%H:%M"), "end": db.strftime("%H:%M")}


def capacity_errors(views, machines, today, extra=None):
    """views: {id: {slots, machine, enabled}}; machines: {code: {max_lives}}; extra: {id: (machine, slot)} = lan
    dang giu gio cu (cung ma phien -> khong dem 2 lan khi trung voi khung moi). Tra [(ids, loi)]."""
    groups, errs = {}, []
    for sid, v in views.items():
        if v.get("enabled") and v["machine"]:
            groups.setdefault(v["machine"], []).append({"id": sid, "slots": v["slots"]})
    for sid, (code, slot) in (extra or {}).items():
        if code and slot:
            groups.setdefault(code, []).append({"id": sid, "slots": [slot]})
    for code, group in groups.items():
        cap = int((machines.get(code) or {}).get("max_lives") or C.DEFAULT_MAX_LIVES)
        seen = set()
        for c in S.capacity_conflicts(group, cap, today):
            k = tuple(c["ids"])
            if k in seen:
                continue
            seen.add(k)
            when = datetime.fromtimestamp(c["start"], _VN).strftime("%d/%m %H:%M")
            errs.append((c["ids"], C.SessMsg.CAPACITY % (code, cap, when, ", ".join(c["ids"]))))
    return errs


def port_errors(views):
    """Hai phien cung may cung cong OBS -> [([id, id_kia], loi)]."""
    seen, errs = {}, []
    for sid, v in sorted(views.items()):
        if v["machine"] and int(v["obs_port"] or 0):
            k = (v["machine"], int(v["obs_port"]))
            if k in seen:
                errs.append(([sid, seen[k]], C.SessMsg.PORT_TAKEN % (k[1], seen[k])))
            seen.setdefault(k, sid)
    return errs


def machine_sync(m, sessions, now, dead_man_s):
    """Trang thai nhan lich cua 1 may: {tone: ok|warn|bad|idle, text, pending, skew}. sessions: moi phien (dict)."""
    code, ver = m["machine_code"], int(m.get("cfg_version") or 0)
    mine = [s for s in sessions if code in (s.get("machine"), (s.get("prev") or {}).get("machine"))]
    pending = [s["id"] for s in mine if int(s.get("published_version") or 0) > ver]
    seen, fetched = float(m.get("hb_last_seen_ts") or 0), float(m.get("cfg_fetched_ts") or 0)
    skew = float(m.get("hb_clock_skew_s") or 0)
    out = {"pending": pending, "skew": skew, "version": ver, "fetched_ts": fetched}
    if not fetched:
        return dict(out, tone="idle", text="Chưa tải lịch lần nào")
    if seen and now - seen > dead_man_s:
        return dict(out, tone="bad", text="Mất liên lạc %d phút" % int((now - seen) // 60))
    if pending:
        return dict(out, tone="warn", text="Chờ nhận · %d phiên đổi" % len(pending))
    return dict(out, tone="ok", text="Đã nhận bản %d · %s" % (ver, datetime.fromtimestamp(fetched, _VN).strftime("%H:%M")))
