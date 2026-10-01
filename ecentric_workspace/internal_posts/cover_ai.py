# Copyright (c) 2026, eCentric and contributors
"""AI tao anh bia cho bai Tin noi bo (PO chot 01/10/2026, mockup v5).

AI doc THANG tieu de + tom tat + noi dung HR da nhap (khong co o goi y) roi ve 3 phuong an.
Gioi han 5 lan / bai / ngay (PO chot) - moi lan bam "Tao anh bia" = mot dong EC Post Cover Job.

Hai buoc, ca hai di qua cong AI chung (platform/ai - MOT nguon khoa, MOT cong tac tat):
  1. gateway.generate(): model chu doc bai -> viet mo ta anh tieng Anh (khong chu, khong logo,
     khong nguoi that, mau eCentric). Model chu hong -> dung mo ta dung san tu tieu de, de HR
     van co anh (khong chan).
  2. images.generate(): model anh tren Kie ve 3 anh 16:9.
Anh Kie tra la tep TAM -> tai ve, luu thanh File CONG KHAI gan vao bai (anh bia cong khai nhu
popup - PO chot). Anh khong duoc chon se bi job don dep xoa sau AI_COVER_KEEP_DAYS ngay.

Chay NEN (queue long): mat 10-60 giay. Trang viet bai hoi trang thai moi 3 giay; HR viet tiep
trong luc cho. Loi -> job Failed + loi de doc; KHONG bao gio chan viec dang bai.
"""
import json

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts.service import Forbidden, NotFound, PostError

PROMPT_SCHEMA = {"type": "object", "properties": {"image_prompt": {"type": "string"}},
                 "required": ["image_prompt"]}
SYSTEM = (
    "You are the art director of eCentric, a Vietnamese e-commerce operations company. "
    "Read an internal company announcement (in Vietnamese) and write ONE English prompt for an "
    "image generator to create its 16:9 cover image. Rules: modern flat or soft 3D editorial "
    "illustration; brand palette navy #2C3DA6, yellow #FFC000, pink #EF7CAF on a light or navy "
    "background; a clear central subject that symbolises the topic; generous empty space; "
    "ABSOLUTELY NO text, letters, numbers, words, signs, logos, watermarks or UI screenshots; no "
    "real people, no recognisable faces (abstract or stylised characters only); professional and "
    "friendly. Reply as JSON {\"image_prompt\": \"...\"} with 40-90 words."
)
FALLBACK = (
    "Modern flat editorial illustration for an internal company announcement about \"%s\". "
    "Brand palette navy #2C3DA6, yellow #FFC000, pink #EF7CAF, light background, clean composition, "
    "abstract symbolic objects, soft shadows, generous empty space, 16:9. No text, no letters, no "
    "logos, no real people."
)
FRIENDLY_ERROR = "AI chưa tạo được ảnh lần này. Bấm Tạo lại sau ít phút, hoặc chọn Màu nền."


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def available():
    try:
        from ecentric_workspace.platform.ai import images
        return images.available()
    except Exception:
        return False


def used_today(post, repo=None):
    repo = _repo(repo)
    return repo.cover_jobs_today(post, repo.today()) if post else 0


def start(user, post, title="", summary="", content="", repo=None):
    """HR bam "Tao anh bia". title/summary/content = cai DANG NHAP tren trang (co the chua luu,
    bai da dang thi luu = doi bai that) -> ghi vao job de AI doc dung cai HR dang thay."""
    repo = _repo(repo)
    if not repo.is_editor(user):
        raise Forbidden("Chỉ HR được dùng AI tạo ảnh bìa.")
    if not post or not repo.post_exists(post):
        raise NotFound(post)
    if not repo.can(post, "write", user):
        raise Forbidden("Bạn không có quyền sửa bài này.")
    if not available():
        raise PostError("AI tạo ảnh đang tắt. Chọn Màu nền hoặc Tải ảnh lên.")
    used = used_today(post, repo)
    if used >= C.AI_COVER_DAILY_LIMIT:
        raise PostError("Bài này đã dùng hết %d/%d lượt tạo ảnh AI hôm nay. Mai thử lại, hoặc chọn Màu nền."
                        % (used, C.AI_COVER_DAILY_LIMIT))
    text = article_text({"title": title, "summary": summary, "content": content})
    if not str(title or "").strip():
        doc = repo.get_post(post)
        text = article_text(doc)
    if not text.strip():
        raise PostError("Nhập tiêu đề bài trước, AI cần đọc bài để vẽ ảnh bìa.")
    job = repo.insert_cover_job(post, user, repo.today(), text)
    repo.enqueue_cover_job(job)
    return {"job": job, "used": used + 1, "limit": C.AI_COVER_DAILY_LIMIT}


def status(user, job, repo=None):
    repo = _repo(repo)
    if not repo.is_editor(user):
        raise Forbidden("Chỉ HR được dùng AI tạo ảnh bìa.")
    row = repo.cover_job(job)
    if not row:
        raise NotFound(job)
    try:
        images = json.loads(row.get("images") or "[]")
    except ValueError:
        images = []
    return {"job": job, "status": row.get("status"), "images": images,
            "error": FRIENDLY_ERROR if row.get("status") == "Failed" else "",
            "used": used_today(row.get("post"), repo), "limit": C.AI_COVER_DAILY_LIMIT}


def article_text(post):
    """Phan bai AI duoc doc: tieu de + tom tat + noi dung (chu tron, cat do dai)."""
    parts = [str(post.get("title") or ""), str(post.get("summary") or ""),
             D.plain_text(post.get("content"), C.AI_TEXT_MAX_CHARS)]
    return "\n\n".join(p for p in parts if p.strip())


def image_prompt(post, generate, text=None):
    """Buoc 1. `generate` = platform.ai.gateway.generate (tiem duoc de test).
    text = noi dung HR dang nhap luc bam (job.source_text); khong co thi doc bai da luu."""
    text = text or article_text(post)
    try:
        res = generate("Bài viết:\n\n" + text, system=SYSTEM, schema=PROMPT_SCHEMA,
                       purpose="post_cover", budget=60)
        p = ((res or {}).get("data") or {}).get("image_prompt") if (res or {}).get("ok") else ""
        if p and len(p.strip()) > 20:
            return p.strip()[:1500], False
    except Exception:
        pass
    # tieu de HR DANG nhap (dong dau cua text) truoc, roi moi toi tieu de da luu
    title = (text or "").split("\n", 1)[0].strip()[:140] or D.plain_text(post.get("title"), 140)
    return FALLBACK % title.replace('"', "'"), True


def run_job(job, repo=None, generate=None, make_images=None):
    """Job nen. Khong nem: moi loi -> job Failed + Error Log."""
    repo = _repo(repo)
    try:
        row = repo.cover_job(job)
        if not row or row.get("status") in ("Done", "Failed"):
            return
        repo.set_cover_job(job, {"status": "Running"})
        post = repo.get_post(row.get("post"))
        if generate is None:
            from ecentric_workspace.platform.ai.gateway import generate
        if make_images is None:
            from ecentric_workspace.platform.ai.images import generate as make_images
        prompt, _fallback = image_prompt(post, generate, row.get("source_text"))
        res = make_images(prompt, n=C.AI_COVER_VARIANTS, aspect_ratio="16:9",
                          timeout=C.AI_COVER_TIMEOUT_SECONDS, poll=C.AI_COVER_POLL_SECONDS)
        saved = []
        for i, url in enumerate((res or {}).get("urls") or []):
            try:
                saved.append(repo.save_remote_image(url, row.get("post"), "ai-bia-%s-%d.png" % (job[:8], i + 1),
                                                    C.AI_COVER_MAX_BYTES))
            except Exception:
                repo.log_error("internal_posts.cover_ai.download")
        fields = {"prompt": prompt, "model": (res or {}).get("model") or "",
                  "images": json.dumps(saved), "status": "Done" if saved else "Failed",
                  "error": "" if saved else ((res or {}).get("error") or "khong luu duoc anh nao")[:1000]}
        repo.set_cover_job(job, fields)
        if not saved:
            repo.log_message("internal_posts.cover_ai.failed", "%s: %s" % (job, fields["error"]))
    except Exception:
        repo.log_error("internal_posts.cover_ai.run_job")
        try:
            repo.set_cover_job(job, {"status": "Failed", "error": "loi he thong - xem Error Log"})
        except Exception:
            pass


def cleanup_unused(repo=None):
    """Job hang ngay: xoa anh AI khong duoc chon lam bia, cu hon AI_COVER_KEEP_DAYS ngay."""
    repo = _repo(repo)
    removed = 0
    for row in repo.old_cover_jobs(C.AI_COVER_KEEP_DAYS):
        try:
            images = json.loads(row.get("images") or "[]")
        except ValueError:
            images = []
        cover = repo.post_cover(row.get("post"))
        keep = [u for u in images if u == cover]
        for url in images:
            if url != cover:
                removed += repo.delete_post_file(url, row.get("post"))
        repo.set_cover_job(row.get("name"), {"images": json.dumps(keep)})
    return removed
