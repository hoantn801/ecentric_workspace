# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 2 - quy tac THUAN (khong cham DB, khong import frappe) cua Data availability:
ten san chuan, ma tran (team x loai du lieu x san), do phu (KPI), do tuoi du lieu, danh sach "Can bo
sung", de xuat data can crawl (han + dem nguoc), ke hoach bo sung (DA-), Thu vien bao cao va goi y
"da co dashboard tuong tu" (so khop tu da bo dau tieng Viet - khong dung AI ngoai).

PO Hoan chot 09/11/2026 - luat chi tiet o README (muc "Dot 2").
"""
import datetime as _dt
import json
import math
import re
import unicodedata

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D

_MAIN = {p.lower(): p for p in C.MAIN_PLATFORMS}


# ------------------------------------------------------------------ san / kenh -----------
def norm_platform(s):
    """"tiktok" / "Tiktok" / " TikTok " -> "TikTok"; san khac giu nguyen (bo khoang trang thua)."""
    s = D.one_line(s, C.PLATFORM_MAX)
    return _MAIN.get(s.lower(), s)


def column_of(platform):
    p = norm_platform(platform)
    return p if p in C.MAIN_PLATFORMS else C.OTHER_PLATFORM


def same(a, b):
    return D.one_line(a, 200).lower() == D.one_line(b, 200).lower()


def channels_of(row):
    return [k for k in C.CHANNEL_KEYS if int((row or {}).get(C.CHANNEL_FIELD[k]) or 0)]


def has_data(row):
    return bool(channels_of(row))


def channel_text(keys, short=True):
    lab = C.CHANNEL_SHORT if short else C.CHANNEL_LABEL
    return " · ".join(lab[k] for k in C.CHANNEL_KEYS if k in (keys or ()))


def load_list(v):
    """Truong Small Text luu JSON list (platforms / channels / availability_rows) -> list."""
    if isinstance(v, (list, tuple)):
        return list(v)
    try:
        out = json.loads(v or "[]")
    except (TypeError, ValueError):
        out = [x.strip() for x in str(v or "").split(",") if x.strip()]
    return out if isinstance(out, list) else []


def platform_label(platforms):
    return ", ".join(platforms or ())


# ------------------------------------------------------------------ do tuoi --------------
def freshness(row, now):
    """-> {state: "" | ok | stale | unknown, label, title}. Chi xet dong DA CO du lieu va co tan suat
    dinh ky. stale = cap nhat lan cuoi cu hon C.FRESH_MAX_HOURS[tan suat]."""
    freq = (row or {}).get("frequency") or ""
    last = D.as_datetime(row.get("last_updated"))
    if not has_data(row):
        return {"state": "", "label": "", "hours": 0}
    limit = C.FRESH_MAX_HOURS.get(freq)
    if not limit:
        return {"state": "ok" if last else "", "label": D.fmt_dt(last) if last else "", "hours": 0}
    if not last:
        return {"state": "unknown", "label": "chưa ghi ngày cập nhật", "hours": 0}
    age = (now - last).total_seconds() / 3600.0
    if age > limit:
        return {"state": "stale", "label": "trễ cập nhật · lần cuối " + D.fmt_dt(last), "hours": int(age)}
    return {"state": "ok", "label": D.fmt_dt(last), "hours": int(age)}


def stale_text(hours):
    return ("%d ngày" % (hours // 24)) if hours >= 48 else ("%d giờ" % hours)


# ------------------------------------------------------------------ do phu (KPI) ---------
def coverage(rows, now=None):
    """KPI dau trang: % dong co tren SharePoint / Data Warehouse / Power BI (tren MOI dong ma tran),
    so dong chua co gi, so dong tre cap nhat."""
    rows = list(rows or ())
    n = len(rows)

    def pct(field):
        return int(round(100.0 * sum(1 for r in rows if int(r.get(field) or 0)) / n)) if n else 0
    out = {"total": n, "sharepoint": pct("in_sharepoint"), "dw": pct("in_dw"), "powerbi": pct("in_powerbi"),
           "empty": sum(1 for r in rows if not has_data(r)),
           "full": sum(1 for r in rows if len(channels_of(r)) == len(C.CHANNEL_KEYS))}
    out["stale"] = sum(1 for r in rows if now and freshness(r, now)["state"] == "stale")
    return out


# ------------------------------------------------------------------ ke hoach dang mo -----
def open_plans(rows, tickets):
    """{ten dong: ticket} - dong co planned_ticket la DA- dang mo (Cho tiep nhan..Cho nghiem thu).
    Ticket da Hoan tat / Huy -> dong khong con "dang lam" (huy ke hoach -> o tro lai "Chua co")."""
    by = {t["name"]: t for t in tickets or () if t.get("status") in C.OPEN}
    out = {}
    for r in rows or ():
        t = by.get(r.get("planned_ticket") or "")
        if t:
            out[r["name"]] = t
    return out


# ------------------------------------------------------------------ ma tran ---------------
def _cell(row, plan, now, names):
    keys = channels_of(row)
    fr = freshness(row, now)
    cell = {"name": row["name"], "platform": norm_platform(row.get("platform")), "has": bool(keys),
            "dots": {k: (k in keys) for k in C.CHANNEL_KEYS}, "fresh": fr["state"], "fresh_label": fr["label"],
            "plan": None, "front": bool(int(row.get("front_priority") or 0))}
    tip = [cell["platform"] + ": " + (channel_text(keys, short=False) or "chưa có")]
    if row.get("frequency"):
        tip.append(row["frequency"])
    if fr["label"]:
        tip.append("cập nhật " + fr["label"] if fr["state"] != "stale" else fr["label"])
    if row.get("data_owner"):
        tip.append("phụ trách " + (names.get(row["data_owner"]) or row["data_owner"]))
    if plan:
        cell["plan"] = {"code": plan["name"], "due": D.fmt_date(plan.get("due_date")),
                        "status": plan.get("status") or "",
                        "assignee": names.get(plan.get("assignee")) or plan.get("assignee") or ""}
        tip.append("đang bổ sung %s · hạn %s" % (plan["name"], cell["plan"]["due"] or "—"))
    cell["state"] = "plan" if (plan and not keys) else ("data" if keys else "none")
    cell["title"] = " · ".join(tip)
    return cell


def matrix(rows, plans, now, names=None):
    """Ma tran theo team (thu tu xuat hien = thu tu seed / tao), moi nhom (team, loai du lieu) mot hang:
    cot Shopee / TikTok / Lazada (moi cot toi da mot dong) + "Khac" (nhieu san, kem ten).
    -> [{team, groups: [{key, team, data_type, cells{Shopee..}, others[], front, note, fresh{..}, flags}]}]"""
    names = names or {}
    teams, order = {}, []
    for r in rows or ():
        team = r.get("team") or ""
        if team not in teams:
            teams[team] = {"team": team, "groups": [], "_idx": {}}
            order.append(team)
        t = teams[team]
        key = (r.get("data_type") or "").strip().lower()
        if key not in t["_idx"]:
            g = {"key": "%s|%s" % (team, r.get("data_type") or ""), "team": team, "data_type": r.get("data_type") or "",
                 "cells": {p: None for p in C.MAIN_PLATFORMS}, "others": [], "front": False, "notes": [],
                 "stale": [], "owners": [], "freqs": [], "last": None, "rows": []}
            t["_idx"][key] = g
            t["groups"].append(g)
        g = t["_idx"][key]
        cell = _cell(r, plans.get(r["name"]), now, names)
        col = column_of(r.get("platform"))
        if col == C.OTHER_PLATFORM or g["cells"].get(col):
            g["others"].append(cell)
        else:
            g["cells"][col] = cell
        g["rows"].append(r["name"])
        g["front"] = g["front"] or cell["front"]
        if (r.get("note") or "").strip() and r["note"].strip() not in g["notes"]:
            g["notes"].append(r["note"].strip())
        if cell["fresh"] == "stale":
            g["stale"].append(cell["platform"])
        if r.get("data_owner") and r["data_owner"] not in g["owners"]:
            g["owners"].append(r["data_owner"])
        if r.get("frequency") and r["frequency"] not in g["freqs"]:
            g["freqs"].append(r["frequency"])
        last = D.as_datetime(r.get("last_updated"))
        if last and has_data(r) and (g["last"] is None or last < g["last"]):
            g["last"] = last          # cu nhat trong nhom (dong co du lieu)
    out = []
    for team in order:
        t = teams.pop(team)
        t.pop("_idx")
        for g in t["groups"]:
            cells = [c for c in list(g["cells"].values()) + g["others"] if c]
            g["full"] = bool(cells) and all(c["has"] and all(c["dots"].values()) for c in cells)
            g["gap"] = any(c["state"] in ("none", "plan") for c in cells)
            g["unplanned"] = [c["platform"] for c in cells if c["state"] == "none"]
            g["planned"] = any(c["plan"] for c in cells)
            g["note"] = " · ".join(g.pop("notes"))
            g["owner_names"] = ", ".join(names.get(u) or u for u in g.pop("owners"))
            g["freq"] = ", ".join(g.pop("freqs"))
            g["last_fmt"] = D.fmt_date(g["last"]) if g["last"] else ""
            g["last"] = D.iso(g["last"]) if g["last"] else ""
            g["search"] = " ".join([g["team"], g["data_type"]] + [c["platform"] for c in cells]).lower()
        out.append(t)
    return out


def groups_flat(teams):
    return [g for t in teams for g in t["groups"]]


# ------------------------------------------------------------------ Can bo sung ----------
def gaps(teams, proposals, plans_by_code=None, names=None):
    """Danh sach "Cần bổ sung" (data CHUA CO): moi nhom co o "Chua co" / dang bo sung, + de xuat Cho
    duyet chua co dong nao trong bang. Nguon: "Đề xuất đã duyệt" > "Đề xuất chờ duyệt" > "Thiếu trong bảng".
    Thieu mot kenh (vd chi chua co Power BI) KHONG vao day - data da co; xem tren ma tran."""
    names = names or {}
    out, idx = [], {}
    for g in groups_flat(teams):
        cells = [c for c in list(g["cells"].values()) + g["others"] if c]
        empty = [c for c in cells if not c["has"]]
        if not empty and not any(c["plan"] for c in cells):
            continue
        plans = []
        for c in cells:
            if c["plan"] and c["plan"]["code"] not in [p["code"] for p in plans]:
                t = (plans_by_code or {}).get(c["plan"]["code"]) or {}
                plans.append({"code": c["plan"]["code"], "assignee": c["plan"]["assignee"],
                              "start": D.fmt_date(t.get("start_date")), "due": c["plan"]["due"]})
        missing_ch = []
        for c in empty:
            for k in C.CHANNEL_KEYS:
                if not c["dots"][k] and k not in missing_ch:
                    missing_ch.append(k)
        item = {"key": g["key"], "team": g["team"], "data_type": g["data_type"],
                "platforms": [c["platform"] for c in empty], "channels": channel_text(missing_ch),
                "unplanned": list(g["unplanned"]), "plans": plans, "source": "table",
                "proposal": "", "urgency": "", "rows": list(g["rows"]), "proposal_open": False}
        idx[g["key"].lower()] = item
        out.append(item)
    for p in proposals or ():
        st = p.get("status")
        if st not in (C.PROP_PENDING, C.PROP_APPROVED):
            continue
        key = ("%s|%s" % (p.get("team") or "", p.get("data_type") or "")).lower()
        item = idx.get(key)
        if st == C.PROP_APPROVED:
            if item:
                item["source"] = "approved"
                if not p.get("resulting_ticket") and not item["proposal_open"]:
                    # de xuat da duyet CHUA co ke hoach -> Len ke hoach se gan vao de xuat nay
                    item.update({"proposal": p["name"], "urgency": p.get("urgency") or "", "proposal_open": True})
            continue
        if item:
            if item["source"] == "table":
                item["source"] = "pending"
            continue
        item = {"proposal_open": False, "key": "%s|%s" % (p.get("team"), p.get("data_type")), "team": p.get("team") or "",
                "data_type": p.get("data_type") or "", "platforms": load_list(p.get("platforms")),
                "channels": channel_text(C.CHANNEL_KEYS), "unplanned": [], "plans": [], "source": "pending",
                "proposal": p["name"], "urgency": p.get("urgency") or "", "rows": [], "only_proposal": True}
        idx[key] = item
        out.append(item)
    for it in out:
        it.setdefault("only_proposal", False)
        it["source_label"] = {"approved": "Đề xuất đã duyệt", "pending": "Đề xuất chờ duyệt",
                              "table": "Thiếu trong bảng"}[it["source"]]
        it["source_css"] = {"approved": "green", "pending": "amber", "table": "gray"}[it["source"]]
    order = {"approved": 0, "pending": 2, "table": 1}
    out.sort(key=lambda it: (0 if it["unplanned"] else 1, order[it["source"]]))
    return out


# ------------------------------------------------------------------ de xuat ---------------
def proposal_due(created, rules, holidays=()):
    """Han duyet = cung gio, sau N ngay lam viec (quy tac "Duyệt đề xuất data cần crawl")."""
    created = D.as_datetime(created)
    n = int(rules["days"].get(C.RULE_PROPOSAL) or 1)
    day = D.add_working_days(created.date(), n, holidays)
    return _dt.datetime.combine(day, created.time().replace(microsecond=0))


def countdown(due_at, now):
    """-> (nhan, qua_han). "còn 4h" / "còn 2 ngày" / "quá hạn 3h"."""
    due_at = D.as_datetime(due_at)
    if not due_at or not now:
        return "", False
    secs = (due_at - now).total_seconds()
    hours = int(math.ceil(abs(secs) / 3600.0))
    span = ("%dh" % hours) if hours <= 24 else ("%d ngày" % int(math.ceil(hours / 24.0)))
    if secs >= 0:
        return "còn " + span, False
    return "quá hạn " + span, True


def proposal_view(p, now, names, tickets=None, files=None):
    st = p.get("status")
    out = {"name": p["name"], "team": p.get("team") or "", "data_type": p.get("data_type") or "",
           "platforms": load_list(p.get("platforms")), "purpose": p.get("purpose") or "",
           "urgency": p.get("urgency") or C.PRI_NORMAL, "urgency_note": p.get("urgency_note") or "",
           "proposer": p.get("proposer") or "", "proposer_name": names.get(p.get("proposer")) or p.get("proposer") or "",
           "created_fmt": D.fmt_dt(p.get("creation")), "status": st, "reason": p.get("reason") or "",
           "decided_by_name": names.get(p.get("decided_by")) or "", "decided_fmt": D.fmt_dt(p.get("decided_at")),
           "ticket": p.get("resulting_ticket") or "", "overdue": False}
    out["platform_text"] = platform_label(out["platforms"])
    if st == C.PROP_PENDING:
        lab, late = countdown(p.get("due_at"), now)
        out.update({"label": "Chờ duyệt · " + lab if lab else "Chờ duyệt", "css": "red" if late else "amber",
                    "overdue": late})
    elif st == C.PROP_APPROVED:
        t = (tickets or {}).get(out["ticket"]) or {}
        if out["ticket"]:
            out["label"] = "Đã duyệt → " + out["ticket"] + (" · xong" if t.get("status") == C.ST_DONE else "")
        else:
            out["label"] = "Đã duyệt · chờ lên kế hoạch"
        out["css"] = "green"
    else:
        out.update({"label": "Từ chối", "css": "gray"})
    out["search"] = " ".join([out["data_type"], out["team"], out["platform_text"], out["proposer_name"]]).lower()
    # chi tiet cho team Data (10/11/2026)
    d_from, d_to = D.as_date(p.get("data_from")), D.as_date(p.get("data_to"))
    rng = ""
    if d_from or d_to:
        rng = "%s – %s" % (D.fmt_date_full(d_from) or "…", D.fmt_date_full(d_to) or "nay")
    chans = [k for k in C.CHANNEL_KEYS if k in load_list(p.get("channels"))]
    out.update({
        "department": p.get("department") or "", "frequency": p.get("frequency") or "",
        "scope": p.get("scope") or "", "links": [x for x in load_list(p.get("source_links")) if isinstance(x, str)],
        "channels": chans, "channel_text": ", ".join(C.CHANNEL_SHORT.get(k, k) for k in chans),
        "range_text": rng, "needed_by": str(p.get("needed_by") or "")[:16],
        "needed_by_fmt": fmt_need(p.get("needed_by")),
        "urgency_reason": p.get("urgency_reason") or "", "files": list(files or ()),
    })
    out["brief"] = proposal_brief(out)
    return out


def parse_platforms(raw, other=""):
    """Checkbox san (+ o "Khác: ...", nhieu san cach dau phay) -> list ten chuan, khong trung."""
    out = []
    items = list(raw or ())
    items += [x for x in re.split(r"[,;/]", other or "") if x.strip()]
    for x in items:
        if not isinstance(x, str) or x.strip() in ("", C.OTHER_PLATFORM):
            continue
        p = norm_platform(x)
        if p and not any(same(p, y) for y in out):
            out.append(p)
    return out


def dept_team(dept, departments=None):
    """Phong ban ERP -> ten team hien tren ma tran: department_name ("Commercial"), khong co thi bo hau to
    cong ty ("Commercial - EC" -> "Commercial")."""
    d = (dept or "").strip()
    lab = (departments or {}).get(d) or ""
    if lab:
        return D.one_line(lab, C.TEAM_MAX)
    return D.one_line(d.rsplit(" - ", 1)[0] if " - " in d else d, C.TEAM_MAX)


_URL_RE = re.compile(r"^https?://[^\s<>\"']+$", re.I)


def parse_links(raw):
    """O "Link nguồn" (moi dong mot link, cho phep cach bang dau phay / khoang trang) -> (links, loi)."""
    items = [x.strip() for x in re.split(r"[\s,]+", raw or "") if x.strip()]
    out, bad = [], []
    for x in items:
        if len(x) > C.LINK_MAX or not _URL_RE.match(x):
            bad.append(x[:60])
        elif x not in out:
            out.append(x)
    return out, bad


def normalize_proposal(data, sent_today=0, departments=None, now=None):
    """Form "Đề xuất data cần crawl" -> dict sach (truong DocType). departments = {ten Department ERP: ten
    hien thi} (service doc tu DB; None = khong kiem ton tai - chi test thuan). now = gio server (kiem "Cần
    trước" phai o tuong lai)."""
    errs = []
    dept = D.one_line(data.get("department"), 140)
    dtype = D.one_line(data.get("data_type"), C.DATA_TYPE_MAX + 1)
    plats = parse_platforms(data.get("platforms") if isinstance(data.get("platforms"), list) else [],
                            data.get("other_platform") or "")
    purpose = D.clean_text(data.get("purpose"), C.PURPOSE_MAX + 1)
    urgency = (data.get("urgency") or C.PRI_NORMAL).strip()
    ureason = D.clean_text(data.get("urgency_reason"), C.REASON_MAX + 1)
    unote = D.clean_text(data.get("urgency_note"), C.REASON_MAX + 1)
    freq = (data.get("frequency") or "").strip()
    scope = D.clean_text(data.get("scope"), C.SCOPE_MAX + 1)
    links, bad_links = parse_links(data.get("source_links"))
    chans = data.get("channels") if isinstance(data.get("channels"), list) else []
    chans = [k for k in C.CHANNEL_KEYS if k in chans]
    d_from, d_to = D.as_date(data.get("data_from")), D.as_date(data.get("data_to"))
    raw_need = str(data.get("needed_by") or "").strip()
    need = D.as_datetime(raw_need.replace("T", " ")) if raw_need else None
    if sent_today >= C.PROPOSAL_DAILY_LIMIT:
        errs.append("Hôm nay bạn đã gửi {0} đề xuất. Mai gửi tiếp nhé.".format(C.PROPOSAL_DAILY_LIMIT))
    if not dept:
        errs.append("Chọn phòng ban cần dữ liệu.")
    elif departments is not None and dept not in departments:
        errs.append("Phòng ban không có trong ERP (hoặc đã ngừng dùng). Chọn lại trong danh sách.")
    if not dtype:
        errs.append("Chọn hoặc ghi loại dữ liệu cần crawl.")
    elif len(dtype) > C.DATA_TYPE_MAX:
        errs.append("Loại dữ liệu dài quá {0} ký tự.".format(C.DATA_TYPE_MAX))
    if not plats:
        errs.append("Chọn ít nhất một sàn.")
    if any(len(p) > C.PLATFORM_MAX for p in plats):
        errs.append("Tên sàn dài quá {0} ký tự.".format(C.PLATFORM_MAX))
    if bad_links:
        errs.append("Link nguồn phải bắt đầu bằng http:// hoặc https:// (sai: {0}).".format(", ".join(bad_links[:3])))
    if len(links) > C.SOURCE_LINKS_MAX:
        errs.append("Tối đa {0} link nguồn.".format(C.SOURCE_LINKS_MAX))
    if len(scope) > C.SCOPE_MAX:
        errs.append("Phạm vi dài quá {0} ký tự.".format(C.SCOPE_MAX))
    if not freq:
        errs.append("Chọn tần suất cập nhật.")
    elif freq not in C.PROP_FREQUENCIES:
        errs.append("Tần suất không hợp lệ.")
    if (data.get("data_from") and not d_from) or (data.get("data_to") and not d_to):
        errs.append("Khoảng dữ liệu: ngày không hợp lệ.")
    elif d_from and d_to and d_to < d_from:
        errs.append("Khoảng dữ liệu: “đến ngày” không được trước “từ ngày”.")
    if raw_need and not need:
        errs.append("“Cần trước” không hợp lệ.")
    elif need and now and need <= now:
        errs.append("“Cần trước” phải là thời điểm trong tương lai.")
    if not purpose:
        errs.append("Ghi dữ liệu này dùng để làm gì (team Data cần để ưu tiên).")
    elif len(purpose) > C.PURPOSE_MAX:
        errs.append("Mục đích dài quá {0} ký tự.".format(C.PURPOSE_MAX))
    if urgency not in C.PROP_URGENCIES:
        errs.append("Mức cần gấp không hợp lệ.")
    elif urgency in C.PROP_URGENCY_NEED_REASON and not ureason:
        errs.append("Mức “{0}” cần ghi lý do cần gấp.".format(urgency))
    if len(ureason) > C.REASON_MAX or len(unote) > C.REASON_MAX:
        errs.append("Lý do cần gấp dài quá {0} ký tự.".format(C.REASON_MAX))
    if errs:
        raise D.Invalid(errs)
    return {"department": dept, "team": dept_team(dept, departments), "data_type": dtype, "platforms": plats,
            "purpose": purpose, "urgency": urgency,
            "urgency_reason": ureason if urgency in C.PROP_URGENCY_NEED_REASON else "",
            "urgency_note": unote, "frequency": freq, "scope": scope, "source_links": links, "channels": chans,
            "data_from": d_from, "data_to": d_to, "needed_by": need}


def fmt_need(v):
    """"Cần trước" -> "17:00 12/12/2026"."""
    x = D.as_datetime(v)
    return x.strftime("%H:%M %d/%m/%Y") if x else ""


def proposal_brief(p):
    """Tom tat ngan cho team Data (bang "Lên kế hoạch" + ghi chu ke hoach). p = proposal_view."""
    bits = []
    if p.get("frequency"):
        bits.append("Tần suất: " + p["frequency"])
    if p.get("scope"):
        bits.append("Phạm vi: " + D.one_line(p["scope"], 120))
    if p.get("range_text"):
        bits.append("Dữ liệu " + p["range_text"])
    if p.get("links"):
        bits.append("%d link nguồn" % len(p["links"]))
    if p.get("files"):
        bits.append("%d tệp hướng dẫn" % len(p["files"]))
    if p.get("needed_by_fmt"):
        bits.append("cần trước " + p["needed_by_fmt"])
    return " · ".join(bits)


# ------------------------------------------------------------------ dong availability -----
def normalize_row(data):
    """O "Sửa dòng dữ liệu" cua team Data. -> dict sach (truong DocType)."""
    errs = []
    team = D.one_line(data.get("team"), C.TEAM_MAX + 1)
    dtype = D.one_line(data.get("data_type"), C.DATA_TYPE_MAX + 1)
    plat = norm_platform(data.get("platform"))
    freq = (data.get("frequency") or "").strip()
    note = D.clean_text(data.get("note"), C.NOTE_MAX + 1)
    last = data.get("last_updated")
    last_dt = D.as_datetime(str(last).replace("T", " ")) if last else None
    if not team or len(team) > C.TEAM_MAX:
        errs.append("Team không hợp lệ (bắt buộc, tối đa {0} ký tự).".format(C.TEAM_MAX))
    if not dtype or len(dtype) > C.DATA_TYPE_MAX:
        errs.append("Loại dữ liệu không hợp lệ (bắt buộc, tối đa {0} ký tự).".format(C.DATA_TYPE_MAX))
    if not plat or plat == C.OTHER_PLATFORM:
        errs.append("Ghi tên sàn / nguồn (Shopee, TikTok, Lazada hoặc nguồn khác như Misa).")
    if freq and freq not in C.FREQUENCIES:
        errs.append("Tần suất không hợp lệ.")
    if len(note) > C.NOTE_MAX:
        errs.append("Ghi chú dài quá {0} ký tự.".format(C.NOTE_MAX))
    if last and not last_dt:
        errs.append("Ngày cập nhật không hợp lệ.")
    if errs:
        raise D.Invalid(errs)
    out = {"team": team, "data_type": dtype, "platform": plat, "frequency": freq, "note": note,
           "front_priority": 1 if _truthy(data.get("front_priority")) else 0,
           "data_owner": (data.get("data_owner") or "").strip(), "last_updated": last_dt}
    for k in C.CHANNEL_KEYS:
        out[C.CHANNEL_FIELD[k]] = 1 if _truthy(data.get(C.CHANNEL_FIELD[k])) else 0
    return out


def _truthy(v):
    return v in (1, True, "1", "true", "True", "on", "yes")


# ------------------------------------------------------------------ ke hoach DA ----------
def normalize_plan(data):
    """Form "Lên kế hoạch bổ sung dữ liệu". Kiem nguoi xu ly / ngay o service (can team + hom nay)."""
    errs = []
    team = D.one_line(data.get("team"), C.TEAM_MAX + 1)
    dtype = D.one_line(data.get("data_type"), C.DATA_TYPE_MAX + 1)
    plats = parse_platforms(data.get("platforms") if isinstance(data.get("platforms"), list) else [],
                            data.get("other_platform") or "")
    chans = [k for k in C.CHANNEL_KEYS if k in (data.get("channels") or ())]
    method = (data.get("method") or C.METHODS[0]).strip()
    note = D.clean_text(data.get("note"), C.BODY_MAX + 1)
    if not team or not dtype:
        errs.append("Thiếu team / loại dữ liệu cần bổ sung.")
    if not plats:
        errs.append("Chọn ít nhất một sàn.")
    if not chans:
        errs.append("Chọn ít nhất một kênh đích (SharePoint / Data Warehouse / Power BI).")
    if method not in C.METHODS:
        errs.append("Cách lấy không hợp lệ.")
    if len(note) > C.BODY_MAX:
        errs.append("Ghi chú dài quá {0} ký tự.".format(C.BODY_MAX))
    if errs:
        raise D.Invalid(errs)
    return {"team": team, "data_type": dtype, "platforms": plats, "channels": chans, "method": method, "note": note,
            "assignee": (data.get("assignee") or "").strip(), "start_date": data.get("start_date") or "",
            "due_date": data.get("due_date") or "", "priority": (data.get("priority") or "").strip(),
            "proposal": (data.get("proposal") or "").strip()}


def da_title(team, data_type, platforms):
    """Tieu de DA = nhan thanh Gantt ("DA Video (Commercial) · Shopee/TikTok/Lazada")."""
    t = "%s (%s) · %s" % (data_type, team, "/".join(platforms or ()))
    return t[:C.TITLE_MAX]


def da_description(team, data_type, platforms, channels, method, note, proposal=None):
    lines = ["Bổ sung dữ liệu %s cho team %s." % (data_type, team),
             "Sàn: %s." % platform_label(platforms),
             "Đưa vào: %s." % channel_text(channels, short=False),
             "Cách lấy: %s." % method]
    if proposal:
        lines.append("Từ đề xuất %s: %s" % (proposal.get("name"), (proposal.get("purpose") or "")[:500]))
    if note:
        lines.append("Ghi chú: " + note)
    return "\n".join(lines)[:C.BODY_MAX]


def flip_values(row, channels, now):
    """Ke hoach DA hoan tat: bat cac kenh da chon cho dong; ghi "cap nhat lan cuoi" = bay gio."""
    vals = {C.CHANNEL_FIELD[k]: 1 for k in channels if k in C.CHANNEL_FIELD}
    vals["last_updated"] = now
    return vals


# ------------------------------------------------------------------ Thu vien bao cao ------
def normalize_library(data):
    errs = []
    title = D.one_line(data.get("title"), C.TITLE_MAX + 1)
    link = (data.get("link") or "").strip()
    team = D.one_line(data.get("team"), C.TEAM_MAX + 1)
    sources = D.clean_text(data.get("data_sources"), C.SOURCES_MAX + 1)
    tags = D.one_line(data.get("tags"), C.TAGS_MAX + 1)
    ticket = (data.get("from_ticket") or "").strip().upper()
    if not title:
        errs.append("Chưa có tên báo cáo.")
    elif len(title) > C.TITLE_MAX:
        errs.append("Tên báo cáo dài quá {0} ký tự.".format(C.TITLE_MAX))
    if not link or len(link) > C.LINK_MAX or not D.valid_link(link):
        errs.append("Link báo cáo phải bắt đầu bằng http:// hoặc https://")
    if len(team) > C.TEAM_MAX:
        errs.append("Tên team dài quá {0} ký tự.".format(C.TEAM_MAX))
    if len(sources) > C.SOURCES_MAX:
        errs.append("Dữ liệu nguồn dài quá {0} ký tự.".format(C.SOURCES_MAX))
    if len(tags) > C.TAGS_MAX:
        errs.append("Thẻ dài quá {0} ký tự.".format(C.TAGS_MAX))
    if errs:
        raise D.Invalid(errs)
    return {"title": title, "link": link, "team": team, "data_sources": sources, "tags": tags, "from_ticket": ticket,
            "report_owner": (data.get("report_owner") or "").strip()}


# ------------------------------------------------------------------ goi y tuong tu --------
#: Tu qua chung (da bo dau) - bo khi so khop de "Dashboard X" khong khop moi dashboard.
STOPWORDS = frozenset("""
cho va cua theo cac nhung mot cai la voi tren trong ve de can lam moi them sua du lieu bao cao dashboard
power bi pbi report data brand so ngay tung nhu tai cung hoac khi thi duoc da dang se tu den sang tao xem the nay
""".split())


def fold(s):
    """Bo dau tieng Viet + chu thuong: "Báo cáo Đơn hàng" -> "bao cao don hang"."""
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


def tokens(s):
    return [w for w in re.findall(r"[a-z0-9]+", fold(s)) if len(w) >= 2 and w not in STOPWORDS]


def similar(q, items, text_of, limit=C.SUGGEST_LIMIT):
    """So khop tu: giu muc co chung >= 2 tu, hoac >= 1 tu khi cau hoi chi co 1-2 tu co nghia (tu dai
    >= 3). Xep theo ti le trung (Jaccard). -> [(diem, muc)]."""
    qt = set(tokens(q))
    if not qt:
        return []
    out = []
    for it in items or ():
        et = set(tokens(text_of(it)))
        shared = qt & et
        if not shared:
            continue
        if len(shared) < 2 and not (len(qt) <= 2 and any(len(w) >= 3 for w in shared)):
            continue
        out.append((round(len(shared) / float(len(qt | et)), 4), it))
    out.sort(key=lambda x: -x[0])
    return out[:limit]
