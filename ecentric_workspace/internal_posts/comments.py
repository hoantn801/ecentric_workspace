# Copyright (c) 2026, eCentric and contributors
"""Binh luan duoi bai Tin noi bo (mockup v6, PO duyet 03/10/2026).

Luat:
  * Ai DOC DUOC bai (da dang) thi binh luan duoc, neu HR de "Cho phep binh luan" (mac dinh bat).
  * Tra loi MOT cap: bam "Tra loi" tren mot tra loi -> van gan vao binh luan goc.
  * Nguoi viet sua / xoa binh luan cua minh. HR AN binh luan (nguoi khac khong thay nua, HR van
    xem duoc noi dung) va hien lai duoc. An binh luan goc = an ca chuoi tra loi cua no.
  * Chuong: binh luan moi -> nguoi dang bai; tra loi -> nguoi viet binh luan goc (+ nguoi dang
    bai). Khong gui cho chinh minh. Event "announcement" = chuong, KHONG Teams.
  * Noi dung la CHU THUONG (khong HTML), toi da COMMENT_MAX_CHARS; chong spam: toi da
    COMMENT_RATE_MAX binh luan / nguoi / bai trong COMMENT_RATE_SECONDS giay.
  * Tim tren binh luan dung lai bang EC Home Reaction (target "cmt:<ten>").

Bang EC Post Comment khong cap quyen cho nhan vien: moi duong doc / ghi di qua day, sau khi
kiem quyen doc BAI (repo.can). `view()` tra du lieu de template comments.html ve.

DUNG CHUNG (04/10/2026, Bang tin): binh luan cua bai Bang tin (EC Social Post) cung nam o bang
EC Post Comment (cot ref_doctype + post la Dynamic Link) va cung chay qua cac ham o day - mot
bang, mot bo luat (tra loi mot cap, sua / xoa, HR an, tim, chong spam, chuong). Phan khac nhau
giua hai loai bai (tai bai, ai doc duoc, duong dan, cau chuong) nam trong "subject": mac dinh
INTERNAL (bai Tin noi bo); social/comments_subject.py cung cap subject cua Bang tin.
"""
import datetime
import hashlib

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts.errors import Forbidden, NotFound, PostError


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def _avatar(user):
    return int(hashlib.md5(str(user or "").encode("utf-8")).hexdigest()[:2], 16) % 4


def enabled(doc):
    return bool(doc.get("published")) and bool(doc.get("allow_comments") if doc.get("allow_comments") is not None else 1)


class InternalSubject:
    """Bai Tin noi bo (EC Internal Post). Cung giao dien voi social.comments_subject.SocialSubject."""
    doctype = C.POST_DT
    dedupe = "internal_post_cmt"

    def load(self, repo, user, name):
        if not name or not repo.post_exists(name):
            raise NotFound(name)
        doc = repo.get_post(name)
        if not repo.can(doc, "read", user):
            raise Forbidden("Bạn không có quyền xem bài này.")
        return doc

    def can_read(self, repo, doc, user):
        return repo.can(doc, "read", user)

    def allowed(self, doc):
        return bool(doc.get("published"))

    def enabled(self, doc):
        return enabled(doc)

    def owner(self, doc):
        return doc.get("owner")

    def url(self, doc):
        return "%s/%s#%s" % (C.ROUTE, doc.get("slug"), C.COMMENT_ANCHOR)

    def titles(self, who, doc):
        t = doc.get("title") or ""
        return ("%s trả lời bình luận của bạn trong bài \"%s\"" % (who, t),
                "%s bình luận bài \"%s\"" % (who, t))

    def moderator(self, repo, user):
        return repo.is_editor(user)


INTERNAL = InternalSubject()


def view(repo, doc, user, editor, subject=None):
    """Khoi binh luan cho trang bai (va cho api ve lai sau moi thao tac)."""
    subject = subject or INTERNAL
    rows = repo.comments_of(doc.get("name"), ref_doctype=subject.doctype) if subject.allowed(doc) else []
    now = repo.now()
    users = [r.get("user") for r in rows] + [user]
    names = repo.full_names(users)
    depts = repo.user_departments(users)
    targets = [C.COMMENT_RX_PREFIX + r["name"] for r in rows]
    likes = {}
    for rx in repo.reactions(targets) if targets else []:
        if rx.get("kind") != C.COMMENT_RX_KIND:
            continue
        slot = likes.setdefault(rx["target"], {"n": 0, "mine": False})
        slot["n"] += 1
        slot["mine"] = slot["mine"] or rx.get("user") == user
    on = subject.enabled(doc)
    owner = subject.owner(doc)

    def item(r):
        lk = likes.get(C.COMMENT_RX_PREFIX + r["name"], {"n": 0, "mine": False})
        nm = names.get(r.get("user")) or r.get("user") or ""
        hidden = bool(r.get("hidden"))
        return {
            "name": r["name"], "user": r.get("user"), "author": nm, "initial": _initials(nm),
            "av": _avatar(r.get("user")), "dept": depts.get(r.get("user")) or "",
            "is_post_author": r.get("user") == owner, "mine": r.get("user") == user,
            "ago": D.ago(r.get("creation"), now), "edited": bool(r.get("edited_on")),
            "content": "" if r.get("deleted") else (r.get("content") or ""),
            "deleted": bool(r.get("deleted")), "hidden": hidden,
            "hidden_label": D.ago(r.get("hidden_on"), now) if hidden else "",
            "likes": lk["n"], "liked": lk["mine"],
            "can_edit": r.get("user") == user and not r.get("deleted") and on,
            "can_hide": editor and not r.get("deleted"),
            "can_reply": on and not r.get("deleted") and not hidden,
            "replies": [],
        }

    roots, by_name = [], {}
    for r in rows:
        if not r.get("parent_comment"):
            it = item(r)
            by_name[r["name"]] = it
            roots.append(it)
    for r in rows:
        p = by_name.get(r.get("parent_comment"))
        if p is None or not r.get("parent_comment"):
            continue
        it = item(r)
        if it["deleted"] or (it["hidden"] and not editor):
            continue
        it["can_reply"] = p["can_reply"] and it["can_reply"]
        p["replies"].append(it)
    items = []
    for it in roots:
        if it["hidden"] and not editor:
            continue                    # an goc = an ca chuoi voi nguoi khong phai HR
        if it["deleted"] and not it["replies"]:
            continue
        items.append(it)
    count = sum(1 for it in items for x in [it] + it["replies"] if not x["deleted"] and not x["hidden"])
    me = names.get(user) or user or ""
    return {"post": doc.get("name"), "enabled": on, "allowed": subject.allowed(doc),
            "count": count, "items": items, "is_editor": editor,
            "me_initial": _initials(me), "me_av": _avatar(user), "max": C.COMMENT_MAX_CHARS,
            "anchor": C.COMMENT_ANCHOR}


def _initials(name):
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[-2][0] + parts[-1][0]).upper()


# ------------------------------------------------------------------ thao tac ------
def _post_for(repo, user, name, subject):
    if not user or user == "Guest":
        raise PostError("Cần đăng nhập")
    return subject.load(repo, user, name)


def _comment_for(repo, user, comment, subject):
    row = repo.comment(comment)
    # Ma binh luan cua LOAI BAI KHAC (vd. goi api Tin noi bo voi binh luan Bang tin) = khong co.
    if not row or (row.get("ref_doctype") or C.POST_DT) != subject.doctype:
        raise PostError("Không tìm thấy bình luận (có thể đã bị xoá).")
    return row, _post_for(repo, user, row.get("post"), subject)


def _clean(content):
    text = str(content or "").replace("\r\n", "\n").strip()
    if not text:
        raise PostError("Bình luận đang trống.")
    if len(text) > C.COMMENT_MAX_CHARS:
        raise PostError("Bình luận dài quá %d ký tự." % C.COMMENT_MAX_CHARS)
    return text


def _result(repo, doc, user, subject):
    return view(repo, doc, user, subject.moderator(repo, user), subject)


def add(user, post, content, parent=None, repo=None, subject=None):
    repo, subject = _repo(repo), subject or INTERNAL
    doc = _post_for(repo, user, post, subject)
    if not subject.enabled(doc):
        raise PostError("Bài này đang tắt bình luận.")
    text = _clean(content)
    root = None
    if parent:
        prow = repo.comment(parent)
        if not prow or prow.get("post") != post or (prow.get("ref_doctype") or C.POST_DT) != subject.doctype:
            raise PostError("Không tìm thấy bình luận để trả lời.")
        if prow.get("parent_comment"):              # tra loi mot cap: gan vao binh luan goc
            prow = repo.comment(prow.get("parent_comment"))
        if not prow or prow.get("deleted") or prow.get("hidden"):
            raise PostError("Bình luận này không còn trả lời được.")
        root = prow
    since = repo.now() - datetime.timedelta(seconds=C.COMMENT_RATE_SECONDS)
    if repo.comment_count_since(post, user, since, ref_doctype=subject.doctype) >= C.COMMENT_RATE_MAX:
        raise PostError("Bạn bình luận hơi nhanh. Đợi một phút rồi gửi tiếp nhé.")
    name = repo.insert_comment(post, user, text, root["name"] if root else None, ref_doctype=subject.doctype)
    _notify(repo, doc, user, name, text, root, subject)
    return _result(repo, doc, user, subject)


def _notify(repo, doc, user, name, text, root, subject):
    url = subject.url(doc)
    who = repo.full_names([user]).get(user) or user
    reply_title, owner_title = subject.titles(who, doc)
    targets = []
    if root and root.get("user") and root.get("user") != user:
        targets.append((root.get("user"), reply_title))
    owner = subject.owner(doc)
    if owner and owner != user and owner not in [t[0] for t in targets]:
        targets.append((owner, owner_title))
    snippet = text if len(text) <= 160 else text[:157].rsplit(" ", 1)[0] + "…"
    for u, title in targets:
        if not subject.can_read(repo, doc, u):        # khong con doc duoc bai: khong gui trich doan
            continue
        try:
            repo.send_bell(C.COMMENT_NOTIFY_EVENT, u, title, snippet, url, doc.get("name"),
                           "%s|%s|%s" % (subject.dedupe, name, u), actor=user, ref_doctype=subject.doctype)
        except Exception:
            repo.log_error("internal_posts.comments.notify")


def edit(user, comment, content, repo=None, subject=None):
    repo, subject = _repo(repo), subject or INTERNAL
    row, doc = _comment_for(repo, user, comment, subject)
    if row.get("user") != user or row.get("deleted"):
        raise Forbidden("Chỉ người viết mới sửa được bình luận.")
    if row.get("hidden"):
        raise PostError("HR đã ẩn bình luận này nên không sửa được.")
    if not subject.enabled(doc):
        raise PostError("Bài này đang tắt bình luận.")
    repo.update_comment(comment, {"content": _clean(content), "edited_on": repo.now()})
    return _result(repo, doc, user, subject)


def delete(user, comment, repo=None, subject=None):
    """Nguoi viet xoa binh luan cua minh (xoa mem: con tra loi thi hien "Bình luận đã bị xoá")."""
    repo, subject = _repo(repo), subject or INTERNAL
    row, doc = _comment_for(repo, user, comment, subject)
    if row.get("user") != user:
        raise Forbidden("Chỉ người viết mới xoá được bình luận.")
    if row.get("hidden"):
        raise PostError("HR đã ẩn bình luận này nên không xoá được.")
    if not row.get("deleted"):
        repo.update_comment(comment, {"deleted": 1, "content": ""})
    return _result(repo, doc, user, subject)


def hide(user, comment, hidden=True, repo=None, subject=None):
    """HR an / hien lai binh luan."""
    repo, subject = _repo(repo), subject or INTERNAL
    if not subject.moderator(repo, user):
        raise Forbidden("Chỉ HR được ẩn bình luận.")
    row, doc = _comment_for(repo, user, comment, subject)
    if hidden:
        repo.update_comment(comment, {"hidden": 1, "hidden_by": user, "hidden_on": repo.now()})
    else:
        repo.update_comment(comment, {"hidden": 0, "hidden_by": None, "hidden_on": None})
    return _result(repo, doc, user, subject)


def like(user, comment, repo=None, subject=None):
    """Tha / bo tim tren binh luan."""
    repo, subject = _repo(repo), subject or INTERNAL
    row, doc = _comment_for(repo, user, comment, subject)
    if row.get("deleted") or (row.get("hidden") and not subject.moderator(repo, user)):
        raise PostError("Bình luận này không còn hiện.")
    target = C.COMMENT_RX_PREFIX + comment
    existing = repo.find_reaction(target, C.COMMENT_RX_KIND, user)
    if existing:
        repo.remove_reaction(existing)
    else:
        try:
            repo.add_reaction(target, C.COMMENT_RX_KIND, user, repo.today())
        except Exception as exc:
            if not repo.is_duplicate(exc):
                raise
    return _result(repo, doc, user, subject)
