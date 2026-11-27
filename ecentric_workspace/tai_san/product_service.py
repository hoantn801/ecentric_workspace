# Copyright (c) 2026, eCentric and contributors
"""Danh muc phan mem (EC Software Product): tao / sua / gop - nguon cua ten, hang, nhom ban quyen.

Hoan 27/11/2026: ban quyen chon phan mem tu dropdown, khong go tay ("Windows 11 Pro" vs "wins 11 pro");
co nut them moi (nguoi quan ly tai san dien Ten, Hang, Nhom, Loai, Ky thanh toan); sau nay gop duoc.
- Trung khoa (bo dau / hoa thuong / khoang trang) -> khong tao, tra ve dong co san de chon.
- Giong ten co san (catalog.similar) -> hoi lai, chi tao khi force.
- Doi ten / hang / nhom -> cap nhat ngay tren moi ban quyen cua phan mem do (ban quyen khong giu ban sao lech).
- Gop A vao B -> moi ban quyen cua A tro sang B, A ngung dung (khong xoa - giu dau vet).
"""
from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import catalog as CAT
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import license_repository as LR
from ecentric_workspace.tai_san import lifecycle as L

FIELDS = ("vendor", "category", "license_type", "billing_cycle", "note")
#: Truong ban quyen lay theo phan mem (ban quyen khong sua rieng).
SYNCED = {"product_name": "license_name", "vendor": "vendor", "category": "category"}


def row(p):
    return {"name": p.name, "label": p.product_name, "vendor": p.vendor, "category": p.category,
            "license_type": p.license_type, "billing_cycle": p.billing_cycle, "disabled": bool(p.disabled)}


def _clean(data):
    v = {}
    for f in FIELDS:
        if f in data:
            val = CAT.clean_name(data[f])[: (500 if f == "note" else 140)]
            v[f] = val or None
    if v.get("category") and v["category"] not in C.LICENSE_CATEGORIES:
        raise L.TransitionError("Nhóm phần mềm không hợp lệ.")
    if v.get("license_type") and v["license_type"] not in C.LICENSE_TYPES:
        raise L.TransitionError("Loại bản quyền không hợp lệ.")
    if v.get("billing_cycle") and v["billing_cycle"] not in C.BILLING_CYCLES:
        raise L.TransitionError("Kỳ thanh toán không hợp lệ.")
    return v


def _name(data):
    name = CAT.clean_name(data.get("product_name"))[:140]
    if len(CAT.name_key(name)) < 2:
        raise L.TransitionError("Nhập tên phần mềm.")
    return name


def create_product(ctx, data, force=False):
    """-> {"product", "row"} khi tao; {"exact": row} khi da co; {"similar": [row...]} khi can hoi lai."""
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản thêm phần mềm.")
    name = _name(data)
    key = CAT.name_key(name)
    hit = LR.product_by_key(key)
    if hit:
        return {"exact": row(hit)}
    v = _clean(data)
    if not force:
        sim = CAT.similar(name, [row(p) for p in LR.products()], C.PRODUCT_SIMILAR_RATIO)
        if sim:
            return {"similar": sim}
    v.update({"product_name": name, "name_key": key, "category": v.get("category") or "Khác",
              "license_type": v.get("license_type") or C.LT_SUBSCRIPTION})
    v["billing_cycle"] = (v.get("billing_cycle") or C.CY_YEARLY) if v["license_type"] == C.LT_SUBSCRIPTION else None
    pid = LR.insert_product(v)
    return {"product": pid, "row": row(LR.product(pid))}


def _sync_licenses(product_name_, p, user, why):
    vals = {lf: p.get(pf) for pf, lf in SYNCED.items()}
    names = LR.license_names_of_product(product_name_)
    for n in names:
        LR.set_license(n, dict(vals, product=p.name))
        LR.add_log(n, why, user)
    return len(names)


def update_product(ctx, name, data):
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản sửa danh mục phần mềm.")
    before = LR.lock_product(name)
    v = _clean(data)
    if "product_name" in data:
        new = _name(data)
        key = CAT.name_key(new)
        other = LR.product_by_key(key)
        if other and other.name != name:
            raise L.TransitionError("Đã có phần mềm \"%s\" - dùng Gộp thay vì đổi tên trùng." % other.product_name)
        v.update({"product_name": new, "name_key": key})
    if "disabled" in data:
        v["disabled"] = 1 if str(data["disabled"]).lower() in ("1", "true", "yes", "on") else 0
    changed = {k: x for k, x in v.items() if (before.get(k) or None) != (x or None)}
    if not changed:
        return {"changed": [], "licenses": 0}
    LR.set_product(name, changed)
    LR.add_product_log(name, "Sửa: " + "; ".join("%s: %s → %s" % (k, before.get(k), x) for k, x in changed.items()
                                                 if k != "name_key"), ctx.user)
    n = 0
    if any(k in changed for k in SYNCED):
        n = _sync_licenses(name, LR.product(name), ctx.user, "Theo danh mục phần mềm: %s" % LR.product(name).product_name)
    return {"changed": [k for k in changed if k != "name_key"], "licenses": n}


def merge_product(ctx, source, target):
    """Gop phan mem `source` vao `target` (ten ghi lech -> mot dong)."""
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản gộp phần mềm.")
    if not source or not target or source == target:
        raise L.TransitionError("Chọn hai phần mềm khác nhau để gộp.")
    src, dst = LR.lock_product(source), LR.lock_product(target)
    if dst.disabled:
        raise L.TransitionError("Phần mềm đích đang ngừng dùng.")
    n = _sync_licenses(source, dst, ctx.user, "Gộp %s vào %s" % (src.product_name, dst.product_name))
    note = ((src.note or "") + ("\n" if src.note else "") + "Đã gộp vào %s (%s)." % (dst.product_name, dst.name))[:500]
    LR.set_product(source, {"disabled": 1, "note": note})
    LR.add_product_log(source, "Gộp vào %s - chuyển %d bản quyền." % (dst.name, n), ctx.user)
    LR.add_product_log(target, "Nhận gộp từ %s (%s) - %d bản quyền." % (src.product_name, src.name, n), ctx.user)
    return {"source": source, "target": target, "licenses": n}


def link_unlinked(ctx):
    """Patch / nut tay: noi moi ban quyen chua co phan mem vao danh muc theo ten (tao dong neu chua co).
    Idempotent: chay lai chi xu ly ban quyen con trong `product`."""
    made, linked = 0, 0
    for lic in LR.licenses_without_product():
        key = CAT.name_key(lic.license_name)
        if not key:
            continue
        p = LR.product_by_key(key)
        if not p:
            pid = LR.insert_product({"product_name": CAT.clean_name(lic.license_name)[:140], "name_key": key,
                                     "vendor": lic.vendor, "category": lic.category or "Khác",
                                     "license_type": lic.license_type or C.LT_SUBSCRIPTION,
                                     "billing_cycle": lic.billing_cycle})
            p, made = LR.product(pid), made + 1
        elif not p.vendor and lic.vendor:
            LR.set_product(p.name, {"vendor": lic.vendor})
            p = LR.product(p.name)
        LR.set_license(lic.name, {"product": p.name, "license_name": p.product_name, "vendor": p.vendor,
                                  "category": p.category})
        linked += 1
    return {"created": made, "linked": linked}
