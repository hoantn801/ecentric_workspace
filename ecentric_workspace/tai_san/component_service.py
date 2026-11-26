# Copyright (c) 2026, eCentric and contributors
"""Linh kien, cau hinh goc va nhap thiet bi moi.

  * Cau hinh goc (CPU, RAM han, SSD theo may...) = bang EC Asset Spec, khong gia.
  * Linh kien MUA THEM = Asset rieng (loai co ec_is_component), lap vao may me qua
    custom_installed_on; khi lap no theo trang thai + nguoi giu cua may me (service.transition
    lan sang linh kien).
"""
from frappe.utils import nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import service as S

MAX_SPEC_ROWS = 30
#: May me o trang thai nay khong nhan linh kien (da ra khoi so dung).
INSTALL_BLOCKED = (C.ST_LOST, C.ST_DISPOSED, C.ST_RETIRED)


def install(ctx, component, parent):
    A.require(ctx.can_manage)
    if component == parent:
        raise L.TransitionError("Không lắp một thiết bị vào chính nó.")
    R.lock_asset(parent)
    R.lock_asset(component)
    comp, mother = R.asset(component), R.asset(parent)
    if mother.get(C.OPS_STATUS_FIELD) in INSTALL_BLOCKED:
        raise L.TransitionError("Máy %s đang %s - không lắp thêm linh kiện."
                                % (mother.get(C.TAG_FIELD) or parent,
                                   C.STATUS_LABELS.get(mother.get(C.OPS_STATUS_FIELD), "")))
    cats = R.categories()
    if not (cats.get(comp.asset_category) or {}).get("ec_is_component"):
        raise L.TransitionError("Loại \"%s\" không phải linh kiện (bật Là linh kiện ở Asset Category)."
                                % comp.asset_category)
    if comp.get(C.INSTALLED_ON_FIELD):
        raise L.TransitionError("Linh kiện đang lắp trong %s - tháo ra trước." % comp.get(C.INSTALLED_ON_FIELD))
    if mother.get(C.INSTALLED_ON_FIELD):
        raise L.TransitionError("Không lắp linh kiện vào một linh kiện khác.")
    if comp.get(C.OPS_STATUS_FIELD) not in (C.ST_AVAILABLE, C.ST_PENDING_CHECK):
        raise L.TransitionError("Chỉ lắp linh kiện đang Sẵn sàng.")
    R.set_asset(component, {C.INSTALLED_ON_FIELD: parent, C.INSTALLED_DATE_FIELD: nowdate(),
                            C.OPS_STATUS_FIELD: mother.get(C.OPS_STATUS_FIELD),
                            "custodian": mother.get("custodian"), "department": mother.get("department")})
    for name, rel in ((component, parent), (parent, component)):
        R.insert_event({"asset": name, "event_type": C.EV_COMPONENT_IN, "related_asset": rel,
                        "to_status": mother.get(C.OPS_STATUS_FIELD), "to_employee": mother.get("custodian"),
                        "note": "%s → %s" % (comp.get(C.TAG_FIELD) or component, mother.get(C.TAG_FIELD) or parent),
                        "actor": ctx.user})
    return {"component": component, "parent": parent}


def remove(ctx, component, to_status=None):
    """Thao linh kien ve kho (Sẵn sàng) hoac danh dau hong (Broken) khi thay do hong."""
    A.require(ctx.can_manage)
    R.lock_asset(component)
    comp = R.asset(component)
    parent = comp.get(C.INSTALLED_ON_FIELD)
    if not parent:
        raise L.TransitionError("Linh kiện này không lắp trong máy nào.")
    status = C.ST_BROKEN if to_status == C.ST_BROKEN else C.ST_AVAILABLE
    R.set_asset(component, {C.INSTALLED_ON_FIELD: None, C.INSTALLED_DATE_FIELD: None,
                            C.OPS_STATUS_FIELD: status, "custodian": None, "department": None,
                            "ec_condition": C.COND_FULL if status == C.ST_BROKEN else comp.get("ec_condition")})
    for name, rel in ((component, parent), (parent, component)):
        R.insert_event({"asset": name, "event_type": C.EV_COMPONENT_OUT, "related_asset": rel,
                        "from_status": comp.get(C.OPS_STATUS_FIELD), "to_status": status if name == component else None,
                        "from_employee": comp.get("custodian"), "actor": ctx.user,
                        "note": "Tháo %s khỏi %s" % (comp.get(C.TAG_FIELD) or component, parent)})
    return {"component": component, "status": status}


def save_specs(ctx, asset_name, rows):
    A.require(ctx.can_manage)
    clean = []
    for r in rows or []:
        part, spec = (r.get("part_type") or "").strip(), (r.get("spec") or "").strip()
        if not part and not spec:
            continue
        if not part or not spec:
            raise L.TransitionError("Mỗi dòng cấu hình cần cả Bộ phận và Thông số.")
        qty = int(r.get("qty") or 1)
        if qty < 1:
            raise L.TransitionError("Số lượng phải từ 1.")
        clean.append({"part_type": part[:140], "spec": spec[:140], "qty": qty,
                      "note": (r.get("note") or "")[:140] or None})
    if len(clean) > MAX_SPEC_ROWS:
        raise L.TransitionError("Tối đa %d dòng cấu hình." % MAX_SPEC_ROWS)
    a = R.asset(asset_name)
    R.replace_specs(asset_name, clean)
    R.insert_event({"asset": asset_name, "event_type": C.EV_SPEC, "to_status": a.get(C.OPS_STATUS_FIELD),
                    "note": "; ".join("%s: %s" % (x["part_type"], x["spec"]) for x in clean)[:1000],
                    "actor": ctx.user})
    return {"rows": len(clean)}


REQUIRED_INTAKE = ("item_code", "asset_name", "purchase_date", "net_purchase_amount")


def create_asset(ctx, data):
    """Nhap thiet bi moi (Draft, is_existing_asset - khong qua Purchase Receipt; khau hao quan tri)."""
    A.require(ctx.can_manage)
    missing = [f for f in REQUIRED_INTAKE if not data.get(f)]
    if missing:
        raise L.TransitionError("Thiếu: " + ", ".join(missing))
    items = {i.name: i for i in R.fixed_asset_items()}
    item = items.get(data["item_code"])
    if not item:
        raise L.TransitionError("Mã hàng không phải tài sản cố định (Item.is_fixed_asset).")
    gross = float(data["net_purchase_amount"])
    if gross <= 0:
        raise L.TransitionError("Nguyên giá phải lớn hơn 0.")
    # Thoi gian khau hao / tien thue: chi Finance dat; nguoi quan ly de trong -> mac dinh theo loai.
    life = data.get("useful_life_months") if ctx.can_finance else None
    rent = data.get("monthly_rent") if ctx.can_finance else None
    S.validate_money(gross, life)
    ownership = data.get("ownership") or C.OWN_COMPANY
    if ownership not in C.OWNERSHIPS:
        raise L.TransitionError("Hình thức sở hữu không hợp lệ.")
    values = {"item_code": item.name, "asset_name": data["asset_name"].strip()[:140],
              "asset_category": data.get("asset_category") or item.asset_category,
              "company": R.default_company(), "location": data.get("location") or R.default_location(),
              "is_existing_asset": 1, "purchase_date": data["purchase_date"],
              "available_for_use_date": data.get("available_for_use_date") or data["purchase_date"],
              "net_purchase_amount": gross, "asset_quantity": 1,
              "calculate_depreciation": 0,
              C.OPS_STATUS_FIELD: C.ST_AVAILABLE, C.TAG_FIELD: (data.get("tag") or "").strip() or None,
              C.SERIAL_FIELD: (data.get("serial") or "").strip() or None,
              "ec_condition": C.COND_GOOD, "ec_ownership": ownership,
              "ec_monthly_rent": rent or None,
              "ec_warranty_until": data.get("warranty_until") or None,
              "ec_supplier": data.get("supplier") or None,
              "ec_useful_life_months": life or None}
    name = R.insert_asset(values)
    if data.get("specs"):
        save_specs(ctx, name, data["specs"])
    R.insert_event({"asset": name, "event_type": C.EV_INTAKE, "to_status": C.ST_AVAILABLE,
                    "ref_doctype": data.get("ref_doctype"), "ref_name": data.get("ref_name"),
                    "note": "Nhập kho %s" % values["asset_name"], "actor": ctx.user})
    return {"asset": name}
