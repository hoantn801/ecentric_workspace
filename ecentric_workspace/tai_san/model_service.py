# Copyright (c) 2026, eCentric and contributors
"""Mau thiet bi (Dell Latitude 5420, MacBook Air M2...) - chon tu danh muc khi Nhap thiet bi.

Hoan 27/11/2026: laptop cung nhu ban quyen - chon tu dropdown, co nut them moi, phan loai duoc.
Danh muc mau = Item goc ERPNext (is_fixed_asset, nhu Asset da tro Item.item_code) - KHONG tao DocType
thu hai. Loai thiet bi = Asset Category (Laptop / PC / Man hinh...), da gan khau hao mac dinh theo loai.
- Trung khoa ten (catalog.name_key) -> khong tao, tra ve mau co san.
- Giong ten -> hoi lai, chi tao khi force.
- Nhom hang / don vi tinh cua Item moi chep tu mot Item tai san co san cung loai (khong hardcode).
"""
from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import catalog as CAT
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repository as R


def row(i):
    return {"name": i.name, "label": i.item_name or i.name, "category": i.asset_category}


def _template(items, category):
    same = [i for i in items if i.asset_category == category and i.item_group and i.stock_uom]
    anyi = [i for i in items if i.item_group and i.stock_uom]
    return (same or anyi or [None])[0]


def create_model(ctx, data, force=False):
    """-> {"item", "row"} khi tao; {"exact": row} khi da co; {"similar": [row...]} khi can hoi lai."""
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản thêm mẫu thiết bị.")
    name = CAT.clean_name(data.get("item_name"))[:140]
    key = CAT.name_key(name)
    if len(key) < 2:
        raise L.TransitionError("Nhập tên mẫu thiết bị.")
    category = data.get("asset_category")
    if not category or category not in R.categories():
        raise L.TransitionError("Chọn loại thiết bị.")
    items = R.fixed_asset_items()
    for i in items:
        if CAT.name_key(i.item_name or i.name) == key:
            return {"exact": row(i)}
    if not force:
        sim = CAT.similar(name, [row(i) for i in items], C.PRODUCT_SIMILAR_RATIO)
        if sim:
            return {"similar": sim}
    tpl = _template(items, category)
    if not tpl:
        raise L.TransitionError("Chưa có mã hàng tài sản nào làm mẫu - nhờ admin tạo một Item tài sản trên Desk.")
    code = CAT.code_for(name, C.MODEL_CODE_PREFIX, R.item_codes())
    item = R.insert_item({"item_code": code, "item_name": name, "description": name,
                          "item_group": tpl.item_group, "stock_uom": tpl.stock_uom,
                          "is_stock_item": 0, "is_fixed_asset": 1, "asset_category": category})
    return {"item": item, "row": {"name": item, "label": name, "category": category}}


def model_item(item_code):
    """Item tai san dang dung duoc (cho nhap / doi mau). None neu khong hop le."""
    return {i.name: i for i in R.fixed_asset_items()}.get(item_code)
