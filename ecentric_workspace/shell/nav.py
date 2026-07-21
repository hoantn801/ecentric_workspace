# Copyright (c) 2026, eCentric and contributors
"""ERP Shell v1 -- Navigation Registry (pure Python, no frappe import).

Contract (Phase 1B): each nav item is a dict with
    key             stable unique id, "<owner>.<slug>"           (required)
    label           display text (vi)                            (required)
    route           unique absolute path, starts with "/"        (required)
    icon            icon name resolved by ec_shell.js ICONS map  (required)
    group           group label; "" = ungrouped top section      (required)
    order           int, sort inside group                       (required)
    active_patterns list of absolute paths; "<base>/*" allowed   (required)
    visible_when    capability string; v1 supports only
                    "internal" (any logged-in internal user)     (required)
    badge_source    optional name of a whitelisted count
                    endpoint; NEVER inline business data         (optional)
    keywords        optional list of plain search synonyms for the
                    shell nav search (labels only, never data)   (optional)
    owner           owning module, e.g. "core", "approval_center"(required)

Rules:
- Business records/data must never be embedded here.
- Visibility here is UX assistance only; backend authorization is unchanged
  and independent (page/API permission still applies on direct URL access).
- compose() is deterministic and rejects duplicate keys or routes.
"""

REQUIRED_FIELDS = (
    "key", "label", "route", "icon", "group", "order",
    "active_patterns", "visible_when", "owner",
)

#: display order of groups; unknown groups sort after these, alphabetically.
GROUP_ORDER = ["", "Phê duyệt", "Chứng từ", "Tạo mới", "GBS", "Hướng dẫn", "Nhân sự"]

CORE_ITEMS = [
    {
        "key": "core.home",
        "label": "Trang chủ",
        "route": "/home",
        "icon": "home",
        "group": "",
        "order": 10,
        "active_patterns": ["/", "/home"],
        "visible_when": "internal",
        "keywords": ["trang chu", "home", "homepage"],
        "owner": "core",
    },
]


def _providers():
    """Module-owned providers, registered centrally."""
    from ecentric_workspace.approval_center import nav as approval_nav
    from ecentric_workspace.legacy_pages import nav as legacy_nav
    from ecentric_workspace.hr import nav as hr_nav
    return [
        ("core", lambda: list(CORE_ITEMS)),
        ("approval_center", approval_nav.items),
        ("legacy_pages", legacy_nav.items),
        ("hr", hr_nav.items),
    ]


# ---------------------------------------------------------------- contexts --
#: Navigation contexts (architecture correction, 2026-07-21). ONE shared
#: chrome; a context only decides WHICH registered items the sidebar shows.
#: - providers: owners whose items belong to the context ("core" everywhere
#:   so "Trang chủ" is always reachable).
#: - entry: module-launcher metadata rendered in the `home` context (and
#:   nowhere else). Adding a future module (pm, alert_center) = one provider
#:   registration + one CONTEXTS entry; shell core stays untouched.
CONTEXTS = {
    "home": {
        "providers": ["core"],
        "launcher": True,          # synthesizes PHÂN HỆ entries from CONTEXTS
        "entry": None,
    },
    "approval_document": {
        "providers": ["core", "approval_center", "legacy_pages"],
        "entry": {"key": "ctx.approval_document", "label": "Phê duyệt & Chứng từ",
                  "route": "/approvals", "icon": "check"},
    },
    "hr": {
        "providers": ["core", "hr"],
        "entry": {"key": "ctx.hr", "label": "Nhân sự",
                  "route": "/ec-hr/attendance", "icon": "doc"},
    },
}
#: order in which specialized contexts are probed for route resolution and in
#: which launcher entries render.
CONTEXT_ORDER = ["approval_document", "hr"]
DEFAULT_CONTEXT = "approval_document"
LAUNCHER_GROUP = "Phân hệ"


def _launcher_items():
    """PHÂN HỆ entries for the `home` context -- derived ONLY from CONTEXTS
    metadata (no second route catalog)."""
    out = []
    for i, name in enumerate(CONTEXT_ORDER):
        e = CONTEXTS[name].get("entry")
        if not e:
            continue
        out.append({
            "key": e["key"], "label": e["label"], "route": e["route"],
            "icon": e.get("icon", "doc"), "group": LAUNCHER_GROUP,
            "order": (i + 1) * 10, "active_patterns": [e["route"]],
            "visible_when": "internal", "owner": "shell.context",
            "keywords": [],
        })
    return out


CHILD_FIELDS = ("key", "label", "route", "icon", "order",
                "active_patterns", "visible_when", "owner")


def _validate_entry(it, seen_keys, seen_routes, is_child=False):
    fields = CHILD_FIELDS if is_child else REQUIRED_FIELDS
    for f in fields:
        if f not in it:
            raise ValueError("nav item missing field %r: %r" % (f, it.get("key")))
    if not isinstance(it["order"], int):
        raise ValueError("nav item %r: order must be int" % it["key"])
    if not it["route"].startswith("/"):
        raise ValueError("nav item %r: route must start with '/'" % it["key"])
    if it["key"] in seen_keys:
        raise ValueError("duplicate nav key: %r" % it["key"])
    if it["route"] in seen_routes:
        raise ValueError("duplicate nav route: %r" % it["route"])
    seen_keys.add(it["key"]); seen_routes.add(it["route"])
    pats = it["active_patterns"]
    if not isinstance(pats, list) or not pats:
        raise ValueError("nav item %r: active_patterns must be non-empty list" % it["key"])
    for pat in pats:
        if not isinstance(pat, str) or not pat.startswith("/"):
            raise ValueError("nav item %r: bad active pattern %r" % (it["key"], pat))
    if it["visible_when"] != "internal":
        raise ValueError("nav item %r: v1 supports visible_when='internal' only" % it["key"])
    kws = it.get("keywords", [])
    if not isinstance(kws, list) or any(not isinstance(k, str) or not k.strip() for k in kws):
        raise ValueError("nav item %r: keywords must be a list of non-empty strings" % it["key"])
    if is_child and "children" in it:
        raise ValueError("nav child %r: nested children are not supported" % it["key"])


def validate(items):
    """Reject malformed/duplicate items (children included -- keys and routes
    are globally unique). Raises ValueError (fail loud, pre-deploy)."""
    seen_keys, seen_routes = set(), set()
    for it in items:
        _validate_entry(it, seen_keys, seen_routes)
        kids = it.get("children", [])
        if kids:
            if not isinstance(kids, list):
                raise ValueError("nav item %r: children must be a list" % it["key"])
            for ch in kids:
                _validate_entry(ch, seen_keys, seen_routes, is_child=True)
    return items


def _group_rank(group):
    try:
        return (GROUP_ORDER.index(group), "")
    except ValueError:
        return (len(GROUP_ORDER), group)


def _compose_owners(owners=None, extra=None):
    items = []
    for owner, provider in _providers():
        if owners is not None and owner not in owners:
            continue
        for it in provider():
            it = dict(it)
            it.setdefault("owner", owner)
            if it.get("children"):
                kids = [dict(ch) for ch in it["children"]]
                for ch in kids:
                    ch.setdefault("owner", owner)
                kids.sort(key=lambda ch: (ch["order"], ch["key"]))
                it["children"] = kids
            items.append(it)
    for it in (extra or []):
        items.append(dict(it))
    validate(items)
    items.sort(key=lambda it: (_group_rank(it["group"]), it["order"], it["key"]))
    return items


def compose(context=None):
    """Deterministic, validated nav list for ONE context (sidebar scope).

    context=None keeps the historical signature and returns DEFAULT_CONTEXT
    (approval_document) -- every pre-context caller keeps its behavior.
    """
    name = context or DEFAULT_CONTEXT
    if name not in CONTEXTS:
        name = DEFAULT_CONTEXT
    ctx = CONTEXTS[name]
    extra = _launcher_items() if ctx.get("launcher") else None
    return _compose_owners(ctx["providers"], extra=extra)


def compose_all():
    """ALL registered real items across every context (global discovery:
    homepage Quick Access + shell search). Synthetic launcher entries are
    EXCLUDED -- they duplicate routes that real items already own."""
    return _compose_owners(owners=None)


def resolve_context(path):
    """Canonical route -> context. Server (fallback regen) and client
    (ec_shell.js port) both use this logic; parity is test-enforced.

    1. Probe specialized contexts (CONTEXT_ORDER) with the SAME matchActive
       scorer over their NON-core items; best positive score wins.
    2. Otherwise "/" and core.home patterns belong to `home`.
    3. Anything else falls back to DEFAULT_CONTEXT (backward compatible for
       unregistered shell adopters).
    """
    p = _norm_path(path)
    best, best_score = None, 0
    for name in CONTEXT_ORDER:
        score = _context_score(name, p)
        if score > best_score:
            best, best_score = name, score
    if best:
        return best
    for pat in CORE_ITEMS[0]["active_patterns"]:
        if _norm_path(pat) == p:
            return "home"
    return DEFAULT_CONTEXT


def _norm_path(p):
    p = (p or "/").split("?")[0].split("#")[0]
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p or "/"


def _context_score(name, path):
    """Best matchActive-style score of `path` against the context's own
    (non-core) items. Mirrors ec_shell.js matchActive scoring."""
    score = 0
    for it in compose(name):
        if it.get("owner") in ("core", "shell.context"):
            continue
        cands = [it] + list(it.get("children") or [])
        for c in cands:
            if _norm_path(c["route"]) == path:
                score = max(score, 1000 + len(c["route"]))
                continue
            for pat in c.get("active_patterns") or []:
                if pat.endswith("/*"):
                    base = _norm_path(pat[:-2])
                    if path == base or path.startswith(base + "/"):
                        score = max(score, 500 + len(base))
                elif _norm_path(pat) == path:
                    score = max(score, 800 + len(pat))
    return score
