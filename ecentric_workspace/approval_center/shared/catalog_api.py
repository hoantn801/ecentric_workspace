# Copyright (c) 2026, eCentric and contributors
"""Approval Center - controlled read API for the catalog page (B2a).

Exposes `list_catalog` and `set_pin` (whitelisted; set_pin only touches the caller's own pins). Normal users never get raw DocType
access (DocPerm is System Manager only); visibility is enforced here via
`shared.catalog_permissions`. Returns just what the page needs.
"""
import frappe
from frappe.utils import getdate, nowdate

from ecentric_workspace.approval_center.shared import catalog_permissions as perms
from ecentric_workspace.guides import registry as guides_registry

CATEGORY_FIELDS = ["name", "category_name", "icon", "sort_order", "is_active"]
PIN_DT = "EC Approval Type Pin"
MAX_PINS = 12
USAGE_DAYS = 90
TOP_USAGE = 8
DEFAULT_PINS = 4
SEEDED_KEY = "ec_apc_pins_seeded"
TYPE_FIELDS = ["name", "approval_title", "description", "icon", "category",
               "card_status", "process_status", "route", "sort_order",
               "visibility_mode", "available_from"]


# Truong song ngu (23/11/2026). Them bang migrate -> truoc khi migrate chay thi KHONG co cot: chi xin
# cot dang ton tai, khong de danh muc vo vi mot cot chua co.
OPTIONAL_TYPE_FIELDS = ["title_vi"]
OPTIONAL_CATEGORY_FIELDS = ["name_vi", "short_name_vi"]


def _with_optional(doctype, base, optional):
    try:
        meta = frappe.get_meta(doctype)
        return base + [f for f in optional if meta.has_field(f)]
    except Exception:
        return base


def _child_map(child_doctype, value_field):
    """parent -> [values] for a child table of EC Approval Type."""
    out = {}
    rows = frappe.get_all(child_doctype,
                          filters={"parenttype": "EC Approval Type"},
                          fields=["parent", value_field])
    for r in rows:
        out.setdefault(r.parent, []).append(r.get(value_field))
    return out


def _shape(t, cat):
    route = t.route if (t.card_status == "Active" and t.route) else None
    # Huong dan su dung cua loai yeu cau nay (None neu chua co bai). Server tra
    # ve, trang KHONG tu doan: danh sach bai nam o guides.registry, mot cho duy
    # nhat, va the o Approval Center chi ve icon "?" khi that su co bai. Chi tra
    # route + ten ngan - trang khong can gi hon.
    guide = guides_registry.guide_for_approval_type(t.name)
    return {
        "guide_route": guide["route"] if guide else None,
        "guide_title": guide["short"] if guide else None,
        "approval_code": t.name,
        "approval_title": t.approval_title,
        # Ten tieng Viet (dong chinh) - trang tu ve approval_title lam dong phu neu khac.
        "title_vi": t.get("title_vi") if hasattr(t, "get") else None,
        "description": t.description,
        "icon": t.icon,
        "category_code": t.category,
        "category_name": cat.category_name if cat else None,
        "category_name_vi": (cat.get("name_vi") if (cat and hasattr(cat, "get")) else None),
        "category_icon": cat.icon if cat else None,
        "card_status": t.card_status,
        "process_status": t.process_status,
        "route": route,
        "sort_order": t.sort_order or 0,
        "category_sort_order": (cat.sort_order or 0) if cat else 0,
    }


@frappe.whitelist()
def list_catalog(include_disabled_admin=0):
    """Return {is_admin, categories, types} visible to the current user."""
    user = frappe.session.user
    if not perms.is_internal_system_user(user):
        return {"is_admin": False, "categories": [], "types": []}

    ctx = perms.build_context(user)
    include_disabled = bool(ctx["is_admin"]) and bool(int(include_disabled_admin or 0))
    today = getdate(nowdate())

    cats = {c.name: c for c in frappe.get_all(
        "EC Approval Category",
        fields=_with_optional("EC Approval Category", CATEGORY_FIELDS, OPTIONAL_CATEGORY_FIELDS))}
    types = frappe.get_all("EC Approval Type",
                           fields=_with_optional("EC Approval Type", TYPE_FIELDS, OPTIONAL_TYPE_FIELDS))
    roles_map = _child_map("EC Approval Type Role", "role")
    depts_map = _child_map("EC Approval Type Department", "department")

    cards = []
    for t in types:
        cat = cats.get(t.category)
        visible = perms.is_type_visible(
            visibility_mode=t.visibility_mode,
            card_status=t.card_status,
            allowed_roles=roles_map.get(t.name, []),
            allowed_departments=depts_map.get(t.name, []),
            available_from=getdate(t.available_from) if t.available_from else None,
            category_is_active=bool(cat.is_active) if cat else False,
            ctx=ctx,
            include_disabled=include_disabled,
            today=today,
        )
        if visible:
            cards.append(_shape(t, cat))

    cards.sort(key=lambda c: (c["category_sort_order"], c["sort_order"],
                              (c["approval_title"] or "")))

    seen = {}
    for c in cards:
        code = c["category_code"]
        if code and code not in seen:
            cat = cats.get(code)
            seen[code] = {
                "category_code": code,
                "category_name": c["category_name"],
                "name_vi": cat.get("name_vi") if (cat and hasattr(cat, "get")) else None,
                "short_name_vi": cat.get("short_name_vi") if (cat and hasattr(cat, "get")) else None,
                "icon": c["category_icon"],
                "sort_order": (cat.sort_order or 0) if cat else 0,
            }
    categories = sorted(seen.values(), key=lambda x: (x["sort_order"], x["category_code"]))

    visible_codes = {c["approval_code"] for c in cards}
    return {"is_admin": bool(ctx["is_admin"]), "categories": categories, "types": cards,
            "my_pins": [c for c in _my_pins(user) if c in visible_codes],
            "my_usage": {k: v for k, v in _my_usage(user).items() if k in visible_codes},
            "pins_seeded": _is_seeded(user)}


# --------------------------------------------------------------------------- #
# Ghim + hay dung (23/11/2026, Hoan chon phuong an A). CHI du lieu cua chinh user
# dang dang nhap; loi -> rong, khong bao gio lam hong danh muc.
# --------------------------------------------------------------------------- #
def _my_pins(user):
    try:
        if not frappe.db.exists("DocType", PIN_DT):
            return []
        return frappe.get_all(PIN_DT, filters={"user": user}, pluck="approval_type",
                              order_by="pinned_at asc, creation asc") or []
    except Exception:
        return []


def _my_usage(user):
    """{approval_type: so phieu CHINH user da gui trong USAGE_DAYS ngay}, TOP_USAGE loai nhieu nhat."""
    try:
        from frappe.utils import add_days, now_datetime
        since = add_days(now_datetime(), -USAGE_DAYS)
        rows = frappe.db.sql(
            """SELECT approval_type, COUNT(*) AS n FROM `tabEC Approval Request`
                WHERE requested_by = %(u)s AND submitted_at >= %(since)s AND IFNULL(approval_type, '') != ''
                GROUP BY approval_type ORDER BY n DESC LIMIT %(lim)s""",
            {"u": user, "since": since, "lim": TOP_USAGE}, as_dict=True) or []
        return {r.approval_type: int(r.n or 0) for r in rows}
    except Exception:
        return {}


def _is_seeded(user):
    try:
        return bool(frappe.defaults.get_user_default(SEEDED_KEY, user))
    except Exception:
        return True     # loi -> coi nhu da gieo, khong tu ghim lung tung


def _mark_seeded(user):
    try:
        frappe.defaults.set_user_default(SEEDED_KEY, "1", user)
    except Exception:
        pass


def _company_top():
    """Loai phieu ca cong ty gui nhieu nhat USAGE_DAYS ngay (cache 1 gio). -> [code, ...]"""
    key = "ec_apc_company_top"
    try:
        hit = frappe.cache().get_value(key)
        if hit is not None:
            return hit
    except Exception:
        hit = None
    try:
        from frappe.utils import add_days, now_datetime
        rows = frappe.db.sql(
            """SELECT approval_type, COUNT(*) AS n FROM `tabEC Approval Request`
                WHERE submitted_at >= %(since)s AND IFNULL(approval_type, '') != ''
                GROUP BY approval_type ORDER BY n DESC LIMIT 12""",
            {"since": add_days(now_datetime(), -USAGE_DAYS)}, as_dict=True) or []
        out = [r.approval_type for r in rows]
    except Exception:
        out = []
    try:
        frappe.cache().set_value(key, out, expires_in_sec=3600)
    except Exception:
        pass
    return out


def default_pins(user, usable_codes):
    """4 loai ghim san (Hoan 23/11): loai CHINH user gui nhieu nhat truoc, thieu thi bu bang loai ca
    cong ty dung nhieu nhat. Chi loai user thay + dung duoc (the Active co route)."""
    picked = []
    mine = sorted(_my_usage(user).items(), key=lambda kv: -kv[1])
    for code in [k for k, _v in mine] + _company_top():
        if code in usable_codes and code not in picked:
            picked.append(code)
        if len(picked) >= DEFAULT_PINS:
            break
    return picked


@frappe.whitelist(methods=["POST"])
def seed_default_pins():
    """Ghim san 4 loai cho user CHUA tung duoc gieo (lan dau mo Approval Center). Chay mot lan / user:
    sau do user tu ghim / bo ghim, khong gieo lai. -> {"my_pins": [...]}"""
    from frappe.utils import now_datetime
    user = frappe.session.user
    if not perms.is_internal_system_user(user):
        return {"my_pins": []}
    if _is_seeded(user):
        return {"my_pins": _my_pins(user)}
    have = _my_pins(user)
    if not have:
        usable = {c["approval_code"] for c in list_catalog().get("types", []) if c.get("route")}
        for code in default_pins(user, usable):
            frappe.get_doc({"doctype": PIN_DT, "user": user, "approval_type": code,
                            "pinned_at": now_datetime()}).insert(ignore_permissions=True)
    _mark_seeded(user)
    return {"my_pins": _my_pins(user)}


@frappe.whitelist(methods=["POST"])
def set_pin(approval_type=None, pinned=1):
    """Ghim / bo ghim mot loai phieu cho CHINH user dang dang nhap. -> {"my_pins": [...]}."""
    from frappe import _
    from frappe.utils import now_datetime
    user = frappe.session.user
    if not perms.is_internal_system_user(user):
        frappe.throw(_("Bạn không có quyền dùng Approval Center."), frappe.PermissionError)
    code = (approval_type or "").strip()
    if not code or not frappe.db.exists("EC Approval Type", code):
        frappe.throw(_("Loại phiếu không tồn tại."))
    want = str(pinned).strip().lower() not in ("0", "false", "no", "")
    rows = frappe.get_all(PIN_DT, filters={"user": user, "approval_type": code}, pluck="name") or []
    if want and not rows:
        if len(_my_pins(user)) >= MAX_PINS:
            frappe.throw(_("Chỉ ghim tối đa {0} loại phiếu. Bỏ ghim bớt rồi thử lại.").format(MAX_PINS))
        frappe.get_doc({"doctype": PIN_DT, "user": user, "approval_type": code,
                        "pinned_at": now_datetime()}).insert(ignore_permissions=True)
    elif not want:
        for n in rows:
            frappe.delete_doc(PIN_DT, n, ignore_permissions=True, force=True)
    _mark_seeded(user)  # da tu ghim / bo ghim -> khong gieo mac dinh nua
    return {"my_pins": _my_pins(user)}



