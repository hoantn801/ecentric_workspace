# Copyright (c) 2026, eCentric and contributors
"""PURE. "Nao" cua Khay: doc mot cau cua nguoi dung -> MOT viec cu the nen lam.

Khay KHONG tu lam gi o day. File nay chi tra loi cau hoi "nguoi nay muon gi", roi:
  * `leave`            -> the don nghi; bam Gui la goi `ec_hr_leave_apply` (luat nghiep vu
                          nghi phep chi nam o do: lui ngay, om can giay, trung ngay...)
  * `payment_request`  -> AI dien ho (`ai_formfill.suggest`) doc tep -> `create_draft` ->
                          nguoi dung mo nhap va tu bam Gui. Hai o "Chi phi hop le?" va o tich
                          xac nhan la PHAN DOAN CUA NGUOI (chot 23/09) - Khay khong gui thay.
  * `answer`           -> tro ly hoi dap co san (`gemini_chat`, quyen theo A14).
  * `clarify`          -> hoi lai mot cau, kem vai lua chon bam duoc.

Khong import frappe: test chay khong can bench.
"""
import datetime
import json

LEAVE = "leave"
PAYMENT = "payment_request"
ANSWER = "answer"
CLARIFY = "clarify"
ACTIONS = (LEAVE, PAYMENT, ANSWER, CLARIFY)

MAX_MESSAGE = 1500
MAX_OPTIONS = 4
MAX_REPLY = 400
#: So ngay lich dua vao prompt. "Thu 6 tuan sau" can toi ~13 ngay; 21 cho du "cuoi thang".
CALENDAR_DAYS = 21

_THU = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "reply": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "leave_type": {"type": "string"},
        "from_date": {"type": "string"},
        "to_date": {"type": "string"},
        "half_day": {"type": "boolean"},
        "half_day_part": {"type": "string", "enum": ["", "morning", "afternoon"]},
        "reason": {"type": "string"},
        "needs_data": {"type": "boolean"},
    },
    "required": ["action", "reply"],
}

SYSTEM = (
    "Ban la {name}, tro ly trong he thong ERP noi bo cua cong ty eCentric (Viet Nam). "
    "Nhiem vu DUY NHAT cua ban o buoc nay: doc cau nguoi dung va chon MOT hanh dong.\n"
    "- leave: nguoi dung muon XIN NGHI (nghi phep, nghi om, nghi viec rieng, nghi bu...). "
    "Dien leave_type bang DUNG MOT ten trong danh sach loai nghi; from_date/to_date dang "
    "YYYY-MM-DD tra theo LICH ben duoi; half_day=true neu nghi nua ngay (sang/chieu, ghi vao "
    "half_day_part). Chua ro ngay hoac loai thi chon clarify, KHONG doan.\n"
    "- payment_request: nguoi dung muon tao DE NGHI THANH TOAN / thanh toan hoa don / chi tien "
    "cho nha cung cap, hoac tha hoa don/bao gia vao va muon tao phieu.\n"
    "- answer: cau hoi hoac tro chuyen. needs_data=true neu can SO LIEU cong ty (bao cao tuan, "
    "diem so, cong viec cua team, tien do) - he thong se tra cuu roi tra loi, reply de trong. "
    "needs_data=false neu chi la chao hoi, cam on, hoi ban la ai, hoi cach dung ERP: tra loi "
    "LUON trong reply (toi da 3 cau, khong bia so lieu).\n"
    "- clarify: thieu thong tin de lam; reply la MOT cau hoi ngan, options la 2-4 cau tra loi "
    "ngan nguoi dung bam duoc.\n"
    "reply: tieng Viet co dau, than thien, toi da 2 cau, xung 'minh' goi 'ban'. KHONG bia so du "
    "phep, ten nguoi duyet hay so tien - he thong se tu dien.\n"
    "Ban KHONG gui don, KHONG tao phieu. Ban chi de xuat; nguoi dung bam nut moi gui."
)


def system(name):
    """Loi dan he thong mang ten tro ly (doi ten = doi mot hang so o khay.py)."""
    return SYSTEM.replace("{name}", str(name or "tro ly"))


def calendar(today, days=CALENDAR_DAYS):
    """-> ['2026-09-28 (Thứ Hai) - hôm nay', ...]. PURE."""
    out = []
    for i in range(days):
        d = today + datetime.timedelta(days=i)
        tag = " - hôm nay" if i == 0 else (" - ngày mai" if i == 1 else "")
        out.append("%s (%s)%s" % (d.isoformat(), _THU[d.weekday()], tag))
    return out


def build_prompt(message, today, leave_types, page="", file_names=()):
    lines = ["LICH:"] + calendar(today)
    lines.append("LOAI NGHI (dung dung ten): " + (", ".join(leave_types) or "(khong co)"))
    if page:
        lines.append("NGUOI DUNG DANG O TRANG: " + str(page)[:120])
    if file_names:
        lines.append("NGUOI DUNG VUA THA %d TEP: %s" % (
            len(file_names), ", ".join(str(n)[:80] for n in list(file_names)[:5])))
    lines.append("CAU CUA NGUOI DUNG: " + str(message)[:MAX_MESSAGE])
    return "\n".join(lines)


def _iso(value):
    try:
        return datetime.date.fromisoformat(str(value or "").strip()[:10])
    except Exception:
        return None


def _clean_options(raw):
    out = []
    for o in raw if isinstance(raw, list) else []:
        s = str(o or "").strip()[:60]
        if s and s not in out:
            out.append(s)
    return out[:MAX_OPTIONS]


def normalize(raw, leave_types, today, has_files=False):
    """Kiem ket qua cua model. Sai hinh -> CLARIFY co cau hoi that, KHONG doan thay model.

    -> {action, reply, options, leave?: {leave_type, from_date, to_date, half_day,
        half_day_date, reason}}
    """
    raw = raw if isinstance(raw, dict) else {}
    action = raw.get("action") if raw.get("action") in ACTIONS else CLARIFY
    reply = str(raw.get("reply") or "").strip()[:MAX_REPLY]
    out = {"action": action, "reply": reply, "options": _clean_options(raw.get("options"))}

    if action == LEAVE:
        why = None
        lt = str(raw.get("leave_type") or "").strip()
        exact = [t for t in leave_types if t.lower() == lt.lower()]
        f, t = _iso(raw.get("from_date")), _iso(raw.get("to_date")) or _iso(raw.get("from_date"))
        if not exact:
            why = ("Bạn muốn nghỉ loại nào?", list(leave_types)[:MAX_OPTIONS])
        elif not f:
            why = ("Bạn muốn nghỉ ngày nào?", ["Ngày mai", "Thứ Sáu tuần này"])
        elif t < f:
            why = ("Ngày kết thúc đang trước ngày bắt đầu, bạn kiểm tra lại giúp mình nhé?", [])
        if why:
            return {"action": CLARIFY, "reply": why[0], "options": why[1]}
        half = bool(raw.get("half_day")) and f == t
        part = raw.get("half_day_part") if raw.get("half_day_part") in ("morning", "afternoon") else ""
        reason = str(raw.get("reason") or "").strip()[:280]
        if half and part:
            reason = ("(Buổi %s) %s" % ("sáng" if part == "morning" else "chiều", reason)).strip()
        out["leave"] = {"leave_type": exact[0], "from_date": f.isoformat(),
                        "to_date": t.isoformat(), "half_day": 1 if half else 0,
                        "half_day_date": f.isoformat() if half else "",
                        "half_day_part": part if half else "", "reason": reason,
                        "past": f < today}
        if not reply:
            out["reply"] = "Mình soạn sẵn đơn rồi, bạn xem lại nhé."
    elif action == PAYMENT and not reply:
        out["reply"] = ("Mình đọc tệp và điền sẵn phiếu cho bạn nhé." if has_files else
                        "Bạn thả hoá đơn hoặc báo giá vào đây, mình điền phiếu giúp.")
    elif action == ANSWER:
        # Chi tra loi thang khi model noi KHONG can so lieu VA da viet cau tra loi. Thieu mot
        # trong hai -> di duong tra cuu (gemini_chat), khong de nguoi dung nhan mot cau rong.
        out["needs_data"] = bool(raw.get("needs_data")) or not reply
    elif action == CLARIFY and not reply:
        out["reply"] = "Bạn nói rõ hơn giúp mình được không?"
    return out


def parse_history(history, max_turns=10):
    """[{role, text}] tu client -> danh sach sach cho gateway. PURE."""
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    out = []
    for h in (history if isinstance(history, list) else [])[-max_turns:]:
        if not isinstance(h, dict):
            continue
        text = str(h.get("text") or "").strip()[:1500]
        if text:
            out.append({"role": "user" if h.get("role") == "user" else "model", "text": text})
    return out
