# Copyright (c) 2026, eCentric and contributors
"""18/11 (tao / sua phien ngay tren /ai-live): kiem tung o cua ngan phien - thuan Python, khong goi DB.
Loi -> AiLiveError(code="field_invalid", data={"field": <ten o>}) de trang hien NGAY DUOI o sai."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S

FIELD_INVALID = "field_invalid"


def fail(field, msg):
    raise C.AiLiveError(msg, FIELD_INVALID, {"field": field})


def text(v):
    return str(v if v is not None else "").strip()


def machine_brands(m):
    return [b.strip() for b in str((m or {}).get("brands") or "").replace(",", "\n").splitlines() if b.strip()]


def live_id(v):
    sid = text(v)
    if not sid:
        fail("live_id", C.SessMsg.NEED_LIVE)
    if not C.SESSION_ID_RE.match(sid):
        fail("live_id", C.ContractMsg.BAD_SESSION_ID)
    return sid


def open_before(v):
    t = text(v)
    if t == "":
        return None
    try:
        n = float(t)
    except ValueError:
        fail("lc_open_before_min", C.SessMsg.BAD_OPEN_BEFORE)
    if n != int(n) or not (C.OPEN_BEFORE_RANGE[0] <= int(n) <= C.OPEN_BEFORE_RANGE[1]):
        fail("lc_open_before_min", C.SessMsg.BAD_OPEN_BEFORE)
    return int(n)


def fields(vals, machine, kit_exists=None):
    """vals: cac o cua phien (chi kiem o co mat). machine: dong EC AI Live Machine (de kiem brand duoc giao).
    Tra dict da chuan hoa (username bo @, chuoi da strip)."""
    out = {}
    if "platform" in vals:
        p = text(vals["platform"])
        if p not in C.PLATFORMS:
            fail("platform", C.SessMsg.BAD_PLATFORM)
        out["platform"] = p
    if "brand" in vals:
        b = text(vals["brand"])
        if not b:
            fail("brand", C.SessMsg.NEED_BRAND)
        if machine is not None and b not in machine_brands(machine):
            fail("brand", C.SessMsg.BRAND_OFF % (b, machine.get("machine_code") or ""))
        out["brand"] = b
    if "tiktok_username" in vals:
        u = text(vals["tiktok_username"]).lstrip("@")
        if u and not C.TIKTOK_USER_RE.match(u):
            fail("tiktok_username", C.SessMsg.BAD_TIKTOK % u)
        out["tiktok_username"] = u          # trong = canh bao vang tren trang (lich tu dong khong mo phong), khong chan
    if "title" in vals:
        t = text(vals["title"])
        if len(t) > C.MAX_SESSION_TITLE:
            fail("title", C.SessMsg.LONG_TITLE % (C.MAX_SESSION_TITLE, len(t)))
        out["title"] = t
    if "shop_name" in vals:
        t = text(vals["shop_name"])
        if len(t) > C.MAX_SHOP_NAME:
            fail("shop_name", C.SessMsg.LONG_SHOP % (C.MAX_SHOP_NAME, len(t)))
        out["shop_name"] = t
    if "mode" in vals:
        md = text(vals["mode"])
        if md not in ("",) + C.MODES:
            fail("mode", C.Msg.BAD_MODE)
        out["mode"] = md
    if "kit" in vals:
        k = text(vals["kit"])
        if k and kit_exists is not None and not kit_exists(k):
            fail("kit", C.SessMsg.BAD_KIT % k)
        out["kit"] = k
    if "watch_url" in vals:
        url = text(vals["watch_url"])
        if url and not C.WATCH_URL_RE.match(url):
            fail("watch_url", C.SessMsg.BAD_URL)
        out["watch_url"] = url
    if "phone_serial" in vals:
        sr = text(vals["phone_serial"])
        if sr and not C.PHONE_SERIAL_RE.match(sr):
            fail("phone_serial", C.SessMsg.BAD_SERIAL)
        out["phone_serial"] = sr
    if "lc_open_before_min" in vals:
        out["lc_open_before_min"] = open_before(vals["lc_open_before_min"])
    return out


def slots(raw, today):
    """Khung gio tu ngan (mang {days|date, start, end, enabled}) -> chuan hoa + khong trung nhau trong phien."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        fail("slots", C.SessMsg.BAD_SLOTS)
    if len(raw) > C.MAX_SESSION_SLOTS:
        fail("slots", C.SessMsg.BAD_SLOT % (C.MAX_SESSION_SLOTS + 1, "tối đa %d khung" % C.MAX_SESSION_SLOTS))
    try:
        out = S.norm_slots(raw)
    except C.AiLiveError as e:
        fail("slots", str(e))
    clash = S.self_overlap(out, today)
    if clash:
        fail("slots", C.SessMsg.SLOT_OVERLAP % (clash[1], clash[0]))
    return out


def default_title(brand, platform, n):
    """Ten mac dinh "<Brand> <San> <so>" khi de trong."""
    return ("%s %s %d" % (brand or "Phiên", platform or "", n)).replace("  ", " ").strip()


def tiktok_warning(platform, username):
    return "Chưa có kênh TikTok – lịch tự động sẽ không mở phòng." if platform == "TikTok" and not username else ""


def live_label(x):
    """Dong trong o "Live tren may": "L1 · Live 1 – TikTok (brand friso)" (bo phan app khong bao)."""
    head = x["live"] + (" · " + x["name"] if x.get("name") and x["name"] != x["live"] else "")
    tail = " – ".join(p for p in [x.get("platform") or ""] if p)
    brand = " (brand %s)" % x["brand"] if x.get("brand") else ""
    return head + (" – " + tail if tail else "") + brand


def machine_lives(known, health_rows, code, now, keep_s):
    """Live may da bao: tu nhip tim (hb_known_lives) + dong tin hieu tung live (live da bao truoc khi co danh sach)."""
    out = {x["live"]: dict(x) for x in known or [] if x.get("live")}
    for h in health_rows or []:
        if h.get("machine") != code or not C.SESSION_ID_RE.match(str(h.get("live") or "")):
            continue
        seen = float(h.get("last_seen_ts") or 0)
        if h["live"] not in out and now - seen <= keep_s:
            out[h["live"]] = {"live": h["live"], "name": "", "platform": "", "brand": h.get("brand") or "", "seen": seen}
    return sorted(out.values(), key=lambda x: x["live"])
