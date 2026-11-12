# Copyright (c) 2026, eCentric and contributors
"""Power-up moi 5 cau (Hoan 13/11/2026). Thuan Python - service doc/ghi qua repo.

Luat:
  * Cong bo xong cau 5, 10, 15, 20 (con cau sau) -> moi nguoi duoc moi 3 skill ngau nhien (rieng
    tung nguoi, hat giong BI MAT phia server) + nut "Bo qua". Chon 1 -> vao TUI (toi da 2 skill
    chua dung; tui day thi khong moi). "Tui vang" cong +300 ngay khi chon.
  * Moi cau hoi, TRUOC khi tra loi, nguoi choi tu bam "Dung" skill trong tui -> co hieu luc tu
    cau do (skill nhieu cau: tinh tu cau kich hoat). Khong bam thi skill van nam trong tui.
  * Server tinh diem; may chi gui id skill. Cau khong cham diem (binh chon, dam may) khong dung
    duoc skill.
Trang thai luu o EC Quiz Player.powers_json:
  {"picked": {"<chi so cau moi>": "<id>|skip"}, "bag": [id, ...],
   "active": [{"id", "from": chi so cau kich hoat, "left": so cau con lai}], "used": [id, ...]}
"""
import hashlib

from ecentric_workspace.dao_tao import constants as C

BAG_MAX = 2
EVERY = 5
GOLD_POINTS = 300
INSURE_POINTS = 500
ELIM_BONUS = 150
GAMBLE_PENALTY = 200
TIME_BONUS_MS = 3000

# id -> (nhan, mo ta ngan, bieu tuong, so cau hieu luc)
CATALOG = {
    "double": ("Nhân đôi", "x2 điểm câu này", "✖️2", 1),
    "eliminate": ("Loại 1 đáp án sai", "Bớt 1 đáp án sai khỏi màn hình của bạn", "✂️", 1),
    "boost5": ("+10% năm câu", "+10% điểm cho 5 câu, tính từ câu dùng", "🚀", 5),
    "shield": ("Khiên chuỗi", "Sai câu này vẫn giữ chuỗi đúng", "🛡️", 1),
    "insure": ("Bảo hiểm", "Sai hoặc hết giờ vẫn được 500 điểm", "🩹", 1),
    "gold": ("Túi vàng", "+300 điểm ngay khi chọn", "💰", 0),
    "gamble": ("Liều ăn nhiều", "Đúng x3 điểm, sai bị trừ 200", "🎲", 1),
    "time": ("Thêm giờ", "Tính điểm như trả lời sớm hơn 3 giây", "⏱️", 1),
    "streak2": ("Chuỗi +2", "Đúng thì chuỗi tăng thêm 2", "🔥", 1),
    "x15": ("x1,5 hai câu", "x1,5 điểm cho 2 câu, tính từ câu dùng", "⚡", 2),
    "steal": ("Đánh cắp", "Lấy 100-300 điểm của người đứng ngay trên bạn", "😈", 1),
    "guard": ("Khiên chặn", "Nằm trong túi là tự chặn 1 lần bị đánh cắp", "🛡️", 0),
}
STEAL_AMOUNTS = (100, 200, 300)
AUTO = ("guard",)                    # skill tu bat khi nam trong tui - khong co nut Dung
IDS = tuple(CATALOG)
SKIP = "skip"
# Loai dap an sai chi co nghia voi cau nhieu lua chon (dung/sai chi co 2 o -> loai 1 la lo dap an).
ELIM_TYPES = (C.Q_SINGLE, C.Q_MULTI)


def enabled(settings):
    return bool((settings or {}).get("power_ups"))


def offer_at(index, total):
    """Cau `index` (0-based) vua cong bo co mo moi power-up khong."""
    return (index + 1) % EVERY == 0 and index + 1 < total


def empty():
    return {"picked": {}, "bag": [], "active": [], "used": []}


def clean_state(raw):
    st = empty()
    raw = raw if isinstance(raw, dict) else {}
    picked = raw.get("picked") if isinstance(raw.get("picked"), dict) else {}
    st["picked"] = {str(k): v for k, v in picked.items() if v in IDS or v == SKIP}
    st["bag"] = [x for x in (raw.get("bag") or []) if x in IDS][:BAG_MAX]
    st["active"] = [a for a in (raw.get("active") or [])
                    if isinstance(a, dict) and a.get("id") in IDS and int(a.get("left") or 0) > 0]
    st["used"] = [x for x in (raw.get("used") or []) if x in IDS][-50:]
    return st


def offer(seed, n=3):
    """3 skill khac nhau, tat dinh theo hat giong BI MAT (rieng nguoi + cau)."""
    return sorted(IDS, key=lambda i: hashlib.sha256(("%s|%s" % (seed, i)).encode("utf-8")).hexdigest())[:n]


def info(pid):
    label, desc, icon, _ = CATALOG[pid]
    return {"id": pid, "label": label, "desc": desc, "icon": icon}


def effective(st, index):
    """Skill dang co hieu luc o cau `index`."""
    return [a["id"] for a in st.get("active") or [] if int(a.get("from", 10 ** 6)) <= index and int(a.get("left") or 0) > 0]


def activate(st, pid, index):
    """Lay skill khoi tui, kich hoat tu cau `index`. -> state moi (khong sua ban vao)."""
    st = clean_state(st)
    if pid not in st["bag"] or pid in AUTO:
        raise ValueError(pid)
    st["bag"].remove(pid)
    st["active"].append({"id": pid, "from": int(index), "left": CATALOG[pid][3]})
    return st


def consume(st, index):
    """Sau khi khoa cau `index` (cau co cham diem): moi skill dang hieu luc bot 1 cau."""
    st = clean_state(st)
    keep = []
    for a in st["active"]:
        if int(a["from"]) <= index:
            a = dict(a, left=int(a["left"]) - 1)
            if a["left"] <= 0:
                st["used"].append(a["id"])
                continue
        keep.append(a)
    st["active"] = keep
    return st


def elapsed_for_score(ids, elapsed_ms):
    return max(0, int(elapsed_ms) - TIME_BONUS_MS) if "time" in ids else elapsed_ms


MULT_MAX = 3.0


def adjust(ids, sc, ratio, prev_streak, qtype):
    """Ap skill vao ket qua scoring.score_answer `sc` (diem, dung, chuoi). -> dict moi.
    ratio None = cau khong cham: khong doi."""
    if ratio is None or not ids:
        return dict(sc)
    out = dict(sc)
    correct = ratio >= 1.0
    pts = float(sc["points"])
    mult = 1.0
    if "double" in ids:
        mult *= 2
    if "boost5" in ids:
        mult *= 1.1
    if "x15" in ids:
        mult *= 1.5
    if "gamble" in ids:
        mult *= 3 if correct else 1
    pts = pts * min(mult, MULT_MAX)             # nhieu skill nhan chong nhau: toi da x3 (QC 13/11)
    if "eliminate" in ids and qtype not in ELIM_TYPES and correct:
        pts += ELIM_BONUS                       # kieu cau khong loai duoc dap an -> doi ra +150 (khi dung)
    if "gamble" in ids and not correct and not ratio:
        pts = -GAMBLE_PENALTY                   # sai han moi tru; dung mot phan giu diem mot phan
    if "insure" in ids and not correct:
        pts = max(pts, INSURE_POINTS)
    if "shield" in ids and not correct:
        out["streak"] = prev_streak
    if "streak2" in ids and correct:
        out["streak"] = int(sc["streak"]) + 2
    out["points"] = int(round(pts))
    return out


def miss_points(ids):
    """Khong tra loi cau co cham diem: bao hiem van cho 500, khien giu chuoi (service xu ly)."""
    return INSURE_POINTS if "insure" in ids else 0


def eliminated(q, ids, seed):
    """Id dap an sai bi an khoi may NGUOI NAY (None neu khong ap dung)."""
    if "eliminate" not in ids or q["type"] not in ELIM_TYPES:
        return None
    right = set(q.get("correct") or [])
    wrong = [o["id"] for o in q.get("options") or [] if o["id"] not in right]
    if not wrong:
        return None
    return sorted(wrong, key=lambda i: hashlib.sha256(("%s|%s" % (seed, i)).encode("utf-8")).hexdigest())[0]


def steal_amount(seed):
    return STEAL_AMOUNTS[int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(STEAL_AMOUNTS)]


def apply_steals(ranked, thieves, amount_for):
    """Danh cap luc khoa cau. ranked = nguoi choi da xep hang (sau khi cong diem cau nay; moi dong
    co user, score, rank, nickname, powers). thieves = user dung "Danh cap" o cau nay. Xu ly tuan tu
    theo hang; nan nhan = nguoi ngay tren (hang 1 thi lay cua hang 2). Khien chan trong tui tu chan
    lan dau. Diem khong am. -> (doi: {user: {"score", "powers"?}}, su kien)."""
    by_rank = {p["rank"]: p for p in ranked}
    rows = {p["user"]: {"score": int(p["score"] or 0), "powers": clean_state(p.get("powers")),
                        "nickname": p.get("nickname") or "", "rank": p["rank"]} for p in ranked}
    changed, events = {}, []
    for user in sorted((u for u in set(thieves) if u in rows), key=lambda u: rows[u]["rank"]):
        me = rows[user]
        tgt = by_rank.get(me["rank"] - 1 if me["rank"] > 1 else 2)
        if not tgt or tgt["user"] == user:
            continue
        vic = rows[tgt["user"]]
        ev = {"thief": user, "victim": tgt["user"], "thief_nick": me["nickname"],
              "victim_nick": vic["nickname"], "amount": 0, "blocked": False}
        if "guard" in vic["powers"]["bag"]:
            vic["powers"]["bag"].remove("guard")
            vic["powers"]["used"].append("guard")
            ev["blocked"] = True
            changed.setdefault(tgt["user"], {})["powers"] = vic["powers"]
        else:
            take = min(int(amount_for(user)), vic["score"])
            vic["score"] -= take
            me["score"] += take
            ev["amount"] = take
            changed.setdefault(tgt["user"], {})["score"] = vic["score"]
            changed.setdefault(user, {})["score"] = me["score"]
        events.append(ev)
    return changed, events
