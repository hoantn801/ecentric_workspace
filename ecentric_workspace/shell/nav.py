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


def compose():
    """Deterministic, validated nav list (visibility filtering happens in api.py)."""
    items = []
    for owner, provider in _providers():
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
    validate(items)
    items.sort(key=lambda it: (_group_rank(it["group"]), it["order"], it["key"]))
    return items
