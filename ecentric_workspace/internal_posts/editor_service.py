# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo - phia NGUOI SOAN (HR): trang viet bai, luu / dang / go, trang quan ly.

Chi EDITOR_ROLES (System Manager, HR Manager, HR User) - kiem o MOI loi vao. Luu bai bang
doc.save() binh thuong (CO kiem quyen role cua Frappe, khong ignore_permissions); quy tac
nghiep vu nam o lifecycle.validate nen form /app va trang viet bai luon giong nhau.

BAO MAT TEP: tep dinh kem + anh bia chi nhan tep DA GAN VAO CHINH BAI NAY (File.attached_to).
Khong co chot nay thi mot nguoi soan co the dan duong dan tep private cua ho so khac vao bai,
va moi nhan vien doc duoc bai se tai duoc tep do (File.has_permission di theo bai).
"""
from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts.service import Forbidden, NotFound, PostError, audience, scope_label

ACTIONS = ("save", "publish", "unpublish")


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def _need_editor(repo, user):
    if not repo.is_editor(user):
        raise Forbidden("Chỉ HR được viết và quản lý bài.")


def _truthy(v):
    return str(v).lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ trang viet bai ----
def dept_options(repo):
    """Phong ban de chon (bo phong da tat), kem do sau de thut le phong con."""
    out, stack = [], []
    for name, (lft, rgt, label, is_group, disabled) in sorted(repo.dept_tree().items(), key=lambda kv: kv[1][0] or 0):
        while stack and lft is not None and stack[-1] < lft:
            stack.pop()
        if not disabled and lft is not None:
            out.append({"name": name, "label": label, "depth": len(stack), "lft": lft, "rgt": rgt})
        if rgt is not None and lft is not None and rgt - lft > 1:
            stack.append(rgt)
    # goc cay ("All Departments") khong phai phong that
    roots = [o for o in out if o["depth"] == 0 and o["rgt"] - o["lft"] > 1]
    if len(roots) == 1 and len(out) > 1:
        out = [dict(o, depth=max(0, o["depth"] - 1)) for o in out if o is not roots[0]]
    return out


def compose_context(user, name=None, repo=None):
    repo = _repo(repo)
    _need_editor(repo, user)
    cats = [D.category_view(r) for r in repo.categories()]
    post = None
    if name:
        if not repo.post_exists(name):
            raise NotFound(name)
        doc = repo.get_post(name)
        depts = [r.get("department") for r in (doc.get("departments") or []) if r.get("department")]
        post = {
            "name": doc.get("name"), "title": doc.get("title") or "", "summary": doc.get("summary") or "",
            "content": repo.safe_html(doc.get("content")), "category": doc.get("category") or "",
            "slug": doc.get("slug") or "", "published": bool(doc.get("published")),
            "pinned": bool(doc.get("pinned")), "expires_on": str(doc.get("expires_on") or ""),
            "notify_bell": bool(doc.get("notify_bell")), "push_to_home": bool(doc.get("push_to_home")),
            "popup_image_link": bool(doc.get("popup_image_link")),
            "notified": bool(doc.get("notified_on")),
            "cover_kind": doc.get("cover_kind") or C.COVER_KIND_COLOR,
            "cover_color": doc.get("cover_color") or "", "cover_icon": bool(doc.get("cover_icon")),
            "cover_image": doc.get("cover_image") or "", "cover_ai": bool(doc.get("cover_ai")),
            "author_label": doc.get("author_label") or "",
            "scope": "dept" if depts else "all", "departments": depts,
            "attachments": [{"file_url": r.get("file_url"), "file_name": r.get("file_name") or ""}
                            for r in (doc.get("attachments") or [])],
            "url": "%s/%s" % (C.ROUTE, doc.get("slug")),
        }
    from ecentric_workspace.internal_posts import cover_ai
    return {
        "post": post, "categories": cats,
        "colors": [{"key": k, "name": v[0], "c1": v[1], "c2": v[2]} for k, v in C.COVER_COLORS.items()],
        "departments": dept_options(repo),
        "employee_lfts": [e["lft"] for e in repo.active_employees() if e["lft"] is not None],
        "company_size": len(repo.active_employees()),
        "ai_limit": C.AI_COVER_DAILY_LIMIT,
        "ai_used": cover_ai.used_today(name, repo=repo) if name else 0,
        "ai_enabled": cover_ai.available(),
    }


# ------------------------------------------------------------------ luu -----------
def _own_file(repo, url, post_name, want_private=None):
    f = repo.file_info(url, post_name)
    if not f:
        return None
    if want_private is not None and bool(f.get("is_private")) != want_private:
        return None
    return f


def save(user, payload, action="save", repo=None):
    """payload: dict tu trang viet bai. -> {name, slug, url, published}."""
    repo = _repo(repo)
    _need_editor(repo, user)
    if action not in ACTIONS:
        raise PostError("Thao tác không hợp lệ")
    p = payload or {}
    name = p.get("name") or None
    doc = repo.get_post(name) if name and repo.post_exists(name) else repo.new_post()
    if name and doc.get("name") != name:
        raise NotFound(name)

    doc.title = str(p.get("title") or "").strip()[:140]
    doc.summary = str(p.get("summary") or "").strip()[:240]
    doc.content = str(p.get("content") or "")
    doc.category = p.get("category") or None
    doc.author_label = str(p.get("author_label") or "").strip()[:80]
    if not doc.get("published_on") or _truthy(p.get("slug_manual")):
        # Chua tung dang: slug di theo tieu de (de trong -> lifecycle sinh lai). Da tung dang: giu.
        doc.slug = D.slugify(p.get("slug")) if _truthy(p.get("slug_manual")) and p.get("slug") else ""
    doc.pinned = 1 if _truthy(p.get("pinned")) else 0
    doc.expires_on = p.get("expires_on") or None
    doc.notify_bell = 1 if _truthy(p.get("notify_bell", 1)) else 0
    doc.push_to_home = 1 if _truthy(p.get("push_to_home", 1)) else 0
    doc.popup_image_link = 1 if _truthy(p.get("popup_image_link", 1)) else 0

    depts = [d for d in (p.get("departments") or []) if d] if p.get("scope") == "dept" else []
    tree = repo.dept_tree()
    bad = [d for d in depts if d not in tree]
    if bad:
        raise PostError("Phòng ban không tồn tại: %s" % ", ".join(bad))
    if p.get("scope") == "dept" and not depts:
        raise PostError("Chọn ít nhất một phòng ban, hoặc để bài cho toàn công ty.")
    doc.set("departments", [{"department": d} for d in depts])

    kind = p.get("cover_kind") if p.get("cover_kind") in (C.COVER_KIND_COLOR, C.COVER_KIND_IMAGE) else C.COVER_KIND_COLOR
    doc.cover_kind = kind
    doc.cover_color = p.get("cover_color") if p.get("cover_color") in C.COVER_COLORS else ""
    doc.cover_icon = 1 if _truthy(p.get("cover_icon", 1)) else 0
    if kind == C.COVER_KIND_IMAGE:
        img = p.get("cover_image") or ""
        if not doc.get("name") or not _own_file(repo, img, doc.get("name"), want_private=False):
            raise PostError("Ảnh bìa phải là ảnh tải lên (hoặc AI tạo) cho chính bài này.")
        doc.cover_image = img
        doc.cover_ai = 1 if _truthy(p.get("cover_ai")) else 0
    else:
        doc.cover_image = ""
        doc.cover_ai = 0

    rows = []
    for a in (p.get("attachments") or [])[:C.MAX_ATTACHMENTS + 1]:
        url = (a or {}).get("file_url") or ""
        f = _own_file(repo, url, doc.get("name"), want_private=True) if doc.get("name") else None
        if not f:
            raise PostError("Tệp đính kèm phải tải lên cho chính bài này (tệp private).")
        rows.append({"file_url": url, "file_name": (a.get("file_name") or f.get("file_name") or "")[:140],
                     "file_size": f.get("file_size") or 0})
    doc.set("attachments", rows)

    if action == "publish":
        doc.published = 1
    elif action == "unpublish":
        doc.published = 0
    repo.save_post(doc)
    return {"name": doc.get("name"), "slug": doc.get("slug"), "published": bool(doc.get("published")),
            "url": "%s/%s" % (C.ROUTE, doc.get("slug"))}


def unpublish(user, name, repo=None):
    repo = _repo(repo)
    _need_editor(repo, user)
    if not repo.post_exists(name):
        raise NotFound(name)
    doc = repo.get_post(name)
    if doc.get("published"):
        doc.published = 0
        repo.save_post(doc)
    return {"name": name, "published": False}


def delete_draft(user, name, repo=None):
    repo = _repo(repo)
    _need_editor(repo, user)
    if not repo.post_exists(name):
        raise NotFound(name)
    doc = repo.get_post(name)
    if doc.get("published") or doc.get("published_on") or doc.get("notified_on"):
        raise PostError("Chỉ xoá được bài nháp chưa từng đăng. Bài đã đăng thì dùng Gỡ.")
    repo.delete_post(name)
    return {"name": name, "deleted": True}


# ------------------------------------------------------------------ quan ly -------
TABS = (("live", "Đang hiện"), ("draft", "Nháp"), ("expired", "Hết hạn"))


def manage_context(user, tab="live", repo=None):
    repo = _repo(repo)
    _need_editor(repo, user)
    today = repo.today()
    rows = repo.list_posts(user)
    cat_map = {r["name"]: r for r in repo.categories(include_disabled=True)}
    names = [r["name"] for r in rows]
    depts = repo.post_departments(names)
    seen_many = repo.seen_users_many(names)
    aud_cache = {}
    groups = {"live": [], "draft": [], "expired": []}
    for r in rows:
        d = tuple(depts.get(r["name"]) or ())
        if d not in aud_cache:
            aud_cache[d] = set(audience(repo, list(d)))
        aud = aud_cache[d]
        seen = len(seen_many.get(r["name"], set()) & aud)
        item = {"name": r["name"], "title": r.get("title") or "", "pinned": bool(r.get("pinned")),
                "category": D.category_view(cat_map.get(r.get("category"))),
                "scope_label": scope_label(repo, list(d)) or "Toàn công ty",
                "date_label": D.date_label(r.get("published_on") or r.get("creation")),
                "url": "%s/%s" % (C.ROUTE, r.get("slug")), "edit_url": "%s?bai=%s" % (C.ROUTE_COMPOSE, r["name"]),
                "seen": seen, "total": len(aud), "pct": int(round(100.0 * seen / len(aud))) if aud else 0,
                "expires_label": D.date_label(r.get("expires_on")), "published": bool(r.get("published")),
                "deletable": not r.get("published") and not r.get("published_on")}
        if not r.get("published"):
            groups["draft"].append(item)
        elif D.expired(r, today):
            groups["expired"].append(item)
        else:
            groups["live"].append(item)
    tab = tab if tab in groups else "live"
    return {"tab": tab, "tabs": [{"key": k, "label": lbl, "count": len(groups[k])} for k, lbl in TABS],
            "items": groups[tab]}
