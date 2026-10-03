# Copyright (c) 2026, eCentric and contributors
"""AI viet giup (mockup v6, PO duyet 03/10/2026).

HR dan vai y chinh (gach dau dong, dan tu tin nhan cung duoc), chon giong van -> AI viet tieu
de + tom tat + noi dung. Trang hien ban xem truoc; HR bam "Dung bai nay" moi thay vao o soan
(JS). Server KHONG ghi gi vao bai.

  * AI chi duoc dung y HR dua, khong tu them so lieu / ngay / ten (luat trong SYSTEM).
  * AI tra JSON co cau truc (muc -> doan mo dau + danh sach); server tu dung HTML va ESCAPE
    moi chuoi - khong in HTML cua model ra trang.
  * Gioi han AI_WRITE_DAILY_LIMIT lan / bai / ngay (bai chua luu: theo nguoi). Chi tinh lan
    AI tra bai duoc - model loi khong mat luot.
  * Goi dong bo qua cong AI chung (platform/ai/gateway) voi ngan sach < 120s cua worker web.
"""
import html

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts.errors import Forbidden, NotFound, PostError

BUDGET = 75
ATTEMPT_TIMEOUT = 45

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "object", "properties": {
            "heading": {"type": "string"},
            "intro": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
            "ordered": {"type": "boolean"},
        }, "required": ["heading"]}},
    },
    "required": ["title", "summary", "sections"],
}

TONE_RULES = {
    "short": "Giọng thông báo ngắn gọn, rõ ràng, lịch sự. 2-3 mục, câu ngắn, mỗi ý một dòng.",
    "steps": "Giọng hướng dẫn từng bước. Mục chính là các bước làm theo thứ tự: dùng ordered = true, "
             "mỗi bước bắt đầu bằng động từ.",
    "friendly": "Giọng thân thiện, gần gũi, có thể vui nhẹ nhưng vẫn rõ ràng. Không dùng tiếng lóng, "
                "tối đa một emoji trong cả bài.",
}

SYSTEM = (
    "Bạn là biên tập viên truyền thông nội bộ của eCentric (công ty vận hành thương mại điện tử ở Việt Nam). "
    "Từ các ý chính HR đưa, viết một bài Tin nội bộ bằng tiếng Việt có dấu, chuẩn chính tả. "
    "LUẬT BẮT BUỘC: chỉ dùng thông tin có trong ý chính; KHÔNG tự thêm số liệu, ngày tháng, tên người, "
    "tên phòng ban, mức tiền, đường link hay chính sách nào không có trong ý chính; ý nào mơ hồ thì viết "
    "chung chung, không đoán. Giữ nguyên mọi con số, ngày, mức tiền như HR viết. "
    "Tiêu đề tối đa 110 ký tự, không dấu chấm cuối. Tóm tắt 1-2 câu, tối đa 220 ký tự. "
    "Nội dung chia 2-4 mục: mỗi mục có heading ngắn, intro (một đoạn, có thể rỗng) và items (gạch đầu dòng, "
    "có thể rỗng). Không chào hỏi kiểu thư, không ký tên. Trả về JSON đúng schema."
)


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def _key(user, post):
    return ("post:%s" % post) if post else ("user:%s" % user)


def quota(user, post, repo=None):
    repo = _repo(repo)
    return {"used": repo.ai_write_used(_key(user, post), repo.today()), "limit": C.AI_WRITE_DAILY_LIMIT}


def write(user, post, points, tone="", repo=None):
    """-> {title, summary, content (HTML), used, limit}."""
    repo = _repo(repo)
    if not repo.is_editor(user):
        raise Forbidden("Chỉ HR được dùng AI viết giúp.")
    if post:
        if not repo.post_exists(post):
            raise NotFound(post)
        if not repo.can(post, "write", user):
            raise Forbidden("Bạn không có quyền sửa bài này.")
    text = str(points or "").strip()
    if len(text) < 10:
        raise PostError("Dán vài ý chính (ít nhất một câu) để AI viết.")
    if len(text) > C.AI_WRITE_POINTS_MAX:
        raise PostError("Ý chính dài quá %d ký tự. Rút gọn bớt rồi thử lại." % C.AI_WRITE_POINTS_MAX)
    tone = tone if tone in C.AI_WRITE_TONES else C.AI_WRITE_TONE_DEFAULT
    if not repo.ai_available():
        raise PostError("AI đang tắt trên hệ thống. Bạn viết tay giúp nhé.")
    key, day = _key(user, post), repo.today()
    used = repo.ai_write_used(key, day)
    if used >= C.AI_WRITE_DAILY_LIMIT:
        raise PostError("Bài này đã dùng hết %d/%d lượt AI viết hôm nay. Mai thử lại nhé."
                        % (used, C.AI_WRITE_DAILY_LIMIT))
    prompt = "Giọng văn: %s. %s\n\nÝ chính của HR:\n%s" % (C.AI_WRITE_TONES[tone], TONE_RULES[tone], text)
    res = repo.ai_generate(prompt, system=SYSTEM, schema=SCHEMA, purpose="post_write",
                           budget=BUDGET, attempt_timeout=ATTEMPT_TIMEOUT) or {}
    data = res.get("data") if res.get("ok") else None
    article = build(data or {})
    if not article:
        repo.log_message("internal_posts.ai_write.failed", (res.get("error") or "JSON rong")[:500])
        raise PostError("AI chưa viết được lần này (không mất lượt). Thử lại sau ít phút.")
    used = repo.ai_write_add(key, day) or used + 1
    article.update(used=used, limit=C.AI_WRITE_DAILY_LIMIT)
    return article


def _s(v, limit):
    t = " ".join(str(v or "").split())
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return t


def build(data):
    """JSON cua model -> {title, summary, content}. Moi chuoi deu escape. None neu khong dung duoc."""
    title = _s(data.get("title"), 140).rstrip(".")
    summary = _s(data.get("summary"), 240)
    parts = []
    for sec in (data.get("sections") or [])[:8]:
        if not isinstance(sec, dict):
            continue
        head = _s(sec.get("heading"), 120)
        intro = _s(sec.get("intro"), 1200)
        items = [_s(x, 600) for x in (sec.get("items") or [])[:15] if _s(x, 600)]
        if not (head or intro or items):
            continue
        if head:
            parts.append("<h2>%s</h2>" % html.escape(head))
        if intro:
            parts.append("<p>%s</p>" % html.escape(intro))
        if items:
            tag = "ol" if sec.get("ordered") else "ul"
            parts.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % html.escape(i) for i in items), tag))
    if not title or not parts:
        return None
    return {"title": title, "summary": summary, "content": "".join(parts)}
