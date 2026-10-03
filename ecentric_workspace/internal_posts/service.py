# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo - phia NGUOI DOC: ghep du lieu cho trang danh sach, trang bai, khoi trang chu,
ghi luot xem, tha cam xuc. Moi ham lay nguoi dung tu tham so `user` do api.py / trang www
truyen tu PHIEN (frappe.session.user) - khong bao gio tu HTTP.

`repo` tiem vao duoc: test chay bang repo gia, khong can bench.
"""
from ecentric_workspace.internal_posts import ack, comments
from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts.audience import audience, scope_label, selected_ranges  # noqa: F401
from ecentric_workspace.internal_posts.errors import Forbidden, NotFound, PostError  # noqa: F401


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def _categories(repo):
    rows = repo.categories()
    return rows, {r["name"]: r for r in rows}


def _cards(repo, user, rows, cat_map, today):
    names = [r["name"] for r in rows]
    depts = repo.post_departments(names)
    seen = repo.seen_by(user, names)
    need = [r["name"] for r in rows if r.get("require_ack") and r.get("published")]
    acked = repo.acked_by(user, need) if need else set()
    # "Can xac nhan" chi cho bai yeu cau CHINH nguoi nay (HR thay moi bai, ke ca phong khac)
    for n in need:
        if n not in acked and user not in audience(repo, depts.get(n) or []):
            acked = acked | {n}
    authors = repo.full_names([r.get("owner") for r in rows])
    out = []
    for r in rows:
        author = r.get("author_label") or authors.get(r.get("owner")) or ""
        out.append(D.card(r, cat_map, seen, today, scope_label(repo, depts.get(r["name"])), author, acked))
    return out


def _legacy(repo, cat_map):
    cat = cat_map.get(C.GUIDES_CATEGORY)
    if not cat:
        return []
    return [D.legacy_card(g, cat) for g in repo.legacy_guides()]


# ------------------------------------------------------------------ danh sach ----
def list_page(user, category="", unseen=False, q="", page=1, repo=None):
    """Context trang /tin-noi-bo. category = ma chuyen muc (?chuyen-muc=), unseen = ?chua-xem=1."""
    repo = _repo(repo)
    today = repo.today()
    editor = repo.is_editor(user)
    rows_cat, cat_map = _categories(repo)
    cats = [D.category_view(r) for r in rows_cat]
    filters = {}
    q = (q or "").strip()[:C.SEARCH_MAX]
    if q:
        filters["title"] = ["like", "%%%s%%" % q]
    rows = repo.list_posts(user, filters=filters)
    cards = _cards(repo, user, rows, cat_map, today)
    legacy = [] if q else _legacy(repo, cat_map)
    everything = cards + legacy
    counts = {c["slug"]: 0 for c in cats}
    for c in everything:
        counts[c["category"]["slug"]] = counts.get(c["category"]["slug"], 0) + 1
    unseen_cards = [c for c in cards if c["unseen"]]
    current = next((c for c in cats if c["slug"] == category), None)
    ctx = {"is_editor": editor, "categories": cats, "counts": counts, "total": len(everything),
           "unseen_count": len(unseen_cards), "q": q, "category": current, "unseen": bool(unseen),
           "mode": "all", "pin": None, "side": [], "sections": [], "items": [], "page_no": 1, "page_count": 1}
    if current or unseen or q:
        pool = unseen_cards if unseen else everything
        if current:
            pool = [c for c in pool if c["category"]["slug"] == current["slug"]]
        pool = D.sort_cards(pool)
        pages = max(1, (len(pool) + C.PAGE_SIZE - 1) // C.PAGE_SIZE)
        try:
            page = int(page or 1)
        except (TypeError, ValueError):
            page = 1
        page = min(max(1, page), pages)
        ctx.update(mode="list", items=pool[(page - 1) * C.PAGE_SIZE:page * C.PAGE_SIZE], page_no=page, page_count=pages)
        return ctx
    pin, side = D.featured(cards)
    ctx.update(pin=pin, side=side, sections=D.sections(everything, cats))
    return ctx


def home_block(user, repo=None):
    """Khoi Tin noi bo tren trang chu: bai ghim truoc roi bai moi nhat (PO chot 6a)."""
    repo = _repo(repo)
    today = repo.today()
    _, cat_map = _categories(repo)
    rows = repo.list_posts(user, filters={"published": 1}, limit=20)
    return D.home_cards(_cards(repo, user, rows, cat_map, today))


# ------------------------------------------------------------------ mot bai ------
def _load(repo, user, slug):
    name = repo.name_by_slug(slug)
    if not name:
        raise NotFound(slug)
    doc = repo.get_post(name)
    if not repo.can(doc, "read", user):
        raise Forbidden(slug)
    return doc


def post_page(user, slug, repo=None):
    repo = _repo(repo)
    doc = _load(repo, user, slug)
    today = repo.today()
    editor = repo.is_editor(user)
    cat_row = repo.category(doc.get("category"))
    cat = D.category_view(cat_row)
    depts = [r.get("department") for r in (doc.get("departments") or []) if r.get("department")]
    body, toc = D.add_heading_ids(repo.safe_html(doc.get("content")))
    owner_name = repo.full_names([doc.get("owner")]).get(doc.get("owner")) or ""
    files = []
    sizes = repo.file_sizes([r.get("file_url") for r in (doc.get("attachments") or [])])
    for r in doc.get("attachments") or []:
        url = r.get("file_url") or ""
        name = r.get("file_name") or url.rsplit("/", 1)[-1]
        ext = (name.rsplit(".", 1)[-1] if "." in name else "").upper()[:4] or "TỆP"
        files.append({"url": url, "name": name, "ext": ext,
                      "size": _size_label(r.get("file_size") or sizes.get(url))})
    return {
        "name": doc.get("name"), "slug": doc.get("slug"), "title": doc.get("title"),
        "summary": doc.get("summary") or "", "category": cat, "body": body, "toc": toc,
        "cover": D.cover(doc.as_dict() if hasattr(doc, "as_dict") else dict(doc), cat_row),
        "author": doc.get("author_label") or owner_name,
        "date_label": D.date_label(doc.get("published_on") or doc.get("creation")),
        "draft": not doc.get("published"), "expired": D.expired(doc, today),
        "expires_label": D.date_label(doc.get("expires_on")), "pinned": bool(doc.get("pinned")),
        "scope_label": scope_label(repo, depts), "files": files,
        "minutes": D.reading_minutes(body), "is_editor": editor,
        "seen": seen_view(repo, doc.get("name"), depts, user, editor),
        "reactions": reactions_view(repo, doc.get("name"), user),
        "editor_info": _editor_info(repo, doc, depts) if editor else None,
        "scheduled": not doc.get("published") and bool(doc.get("publish_at")),
        "publish_at_label": D.when_label(doc.get("publish_at")),
        "ack": ack.view(repo, doc, user, editor),
        "comments": comments.view(repo, doc, user, editor),
    }


def _size_label(n):
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n < 1024 * 1024:
        return "%d KB" % max(1, round(n / 1024.0))
    return ("%.1f MB" % (n / 1024.0 / 1024.0)).replace(".", ",")


def _editor_info(repo, doc, depts=()):
    start = D.as_datetime(doc.get("publish_at"))
    popup_window = ""
    if doc.get("push_to_home") and not depts and start and not doc.get("published"):
        a, b = D.popup_window(start.date(), doc.get("expires_on"))
        popup_window = "%s – %s" % (D.short_date(a), D.short_date(b))
    return {"notified_label": D.date_label(doc.get("notified_on")) if doc.get("notified_on") else "",
            "notify_bell": bool(doc.get("notify_bell")),
            "notify_teams": bool(doc.get("notify_bell")) and bool(doc.get("notify_teams")),
            "popup": bool(doc.get("push_to_home")) and repo.popup_published(doc.get("home_announcement")),
            "popup_planned": bool(doc.get("push_to_home")) and not depts,
            "popup_window": popup_window,
            "publish_at_short": D.short_when(doc.get("publish_at")),
            "edit_url": "%s?bai=%s" % (C.ROUTE_COMPOSE, doc.get("name"))}


def seen_view(repo, name, depts, user, editor):
    aud = audience(repo, depts)
    seen = repo.seen_users(name)
    names = repo.full_names(list(seen) + (list(aud) if editor else []))
    s = D.seen_summary(aud, seen, names, user, editor)
    s["line"] = D.seen_line(s)
    for f in s["faces"]:
        f["initial"] = D.initials(f["name"])
    return s


def mark_seen(user, name, repo=None):
    """Nguoi dang dang nhap vua mo bai -> ghi luot xem. Tra so dem moi de trang cap nhat."""
    repo = _repo(repo)
    if not user or user == "Guest":
        raise PostError("Cần đăng nhập")
    if not repo.post_exists(name):
        raise PostError("Không tìm thấy bài")
    doc = repo.get_post(name)
    if not repo.can(doc, "read", user):
        raise PostError("Bạn không có quyền xem bài này")
    first = repo.mark_seen(name, user) if doc.get("published") else False
    depts = [r.get("department") for r in (doc.get("departments") or []) if r.get("department")]
    s = seen_view(repo, name, depts, user, False)
    return {"first": bool(first), "seen": s["seen"], "total": s["total"], "not_seen": s["not_seen"],
            "pct": s["pct"]}


# ------------------------------------------------------------------ cam xuc ------
def reactions_view(repo, name, user):
    from ecentric_workspace.home_today import domain as HD
    target = C.REACTION_TARGET_PREFIX + name
    rows = repo.reactions([target])
    names = repo.full_names([r.get("user") for r in rows])
    per = HD.reactions_view(rows, [target], user, names)[target]
    items, who, total = [], [], 0
    for kind in C.REACTION_KINDS:
        slot = per[kind]
        total += slot["n"]
        items.append({"kind": kind, "emoji": C.REACTION_EMOJI[kind], "label": C.REACTION_LABELS[kind],
                      "n": slot["n"], "mine": slot["mine"]})
    for r in rows:                       # nguoi tha (khac toi), moi nguoi mot lan, theo thu tu tha
        u = r.get("user")
        if u and u != user and u not in who:
            who.append(u)
    who_names = [names.get(u) or u for u in who]
    return {"items": items, "total": total, "who": D.who_line(who_names, total, any(i["mine"] for i in items))}


def toggle_reaction(user, name, kind, repo=None):
    repo = _repo(repo)
    if not user or user == "Guest":
        raise PostError("Cần đăng nhập")
    if kind not in C.REACTION_KINDS:
        raise PostError("Cảm xúc không hợp lệ")
    if not repo.post_exists(name):
        raise PostError("Không tìm thấy bài")
    doc = repo.get_post(name)
    if not doc.get("published") or not repo.can(doc, "read", user):
        raise PostError("Bạn không có quyền với bài này")
    target = C.REACTION_TARGET_PREFIX + name
    existing = repo.find_reaction(target, kind, user)
    if existing:
        repo.remove_reaction(existing)
    else:
        try:
            repo.add_reaction(target, kind, user, repo.today())
        except Exception as exc:        # bam 2 tab cung luc -> coi nhu da bat
            if not repo.is_duplicate(exc):
                raise
    return reactions_view(repo, name, user)
