# Copyright (c) 2026, eCentric and contributors
"""12/11/2026: ma brand TRONG SO HOP DONG KOL/KOC tach khoi Brand.ec_brand_code.

Thu luong tren site 12/11: so hop dong lay Brand.ec_brand_code - ma cua bao cao NMV / alerts
(AND-VN, DUT, VTD-VN...) chu khong phai ma cua tool cu (tab BRAND CODE: AND, DL, VITA...).
Doi ec_brand_code la vo bao cao, nen them truong rieng Brand.ec_contract_code (cung khai trong
fixtures) va nap 20 ma cua tab BRAND CODE theo map PO chot 12/11:
  * VEYONS / VEYO -> VEY-VN (ten brand tren ERP la VEYO -> ma VEYO);
  * Ngu Coc Vinasoy -> VNS-VN;
  * chua co brand thi tao them: FRL-VN (France Lait - ban cu "France Lait" dang Inactive)
    va DLC-VN (Delical). Brand moi KHONG dat ec_brand_code (khong lan vao bao cao / alerts).

Chi dien ma khi o con TRONG: Ke toan da sua tay thi giu. Chay lai nhieu lan an toan. Khong nem loi:
loi tung brand ghi Error Log, cac brand khac van chay.
"""
import frappe

FIELD = "ec_contract_code"

# Brand ERP -> ma trong so hop dong (tab BRAND CODE cua sheet "TOOL TAO HDDV & BBNT").
CODES = (
    ("DUT-VN", "DL"), ("FRI-VN", "FRISO"), ("VTD-VN", "VITA"), ("ABBOTT", "ABBOTT"),
    ("WMR-VN", "WM"), ("LOF-VN", "LOF"), ("PAV-VN", "PVD"), ("VEY-VN", "VEYO"),
    ("FRL-VN", "FRL"), ("DLC-VN", "DLC"), ("PAW-VN", "PAW"), ("Pin Hà Nội", "PHN"),
    ("SGP - Sài Gòn Paper", "SGP"), ("VNS-VN", "NCDD"), ("Anlene", "ANL"), ("PON-VN", "PONNIE"),
    ("Sensodyne", "SSD"), ("Tempo", "TEMPO"), ("AND-VN", "AND"),
)
# Brand chua co tren ERP -> tao (ten, ten day du).
NEW_BRANDS = (("FRL-VN", "France Lait"), ("DLC-VN", "Delical"))


def _ensure_field():
    if frappe.get_meta("Brand").has_field(FIELD):
        return
    # Fixtures dong bo SAU patch trong bench migrate -> tao truoc o day, cung dinh nghia voi fixtures.
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    create_custom_field("Brand", {
        "fieldname": FIELD, "label": "Mã trong số HĐ", "fieldtype": "Data", "insert_after": "ec_brand_name",
        "description": "Ma brand in trong so hop dong KOL/KOC (vd DL, FRISO). Khac Brand Code cua bao cao.",
    })
    frappe.clear_cache(doctype="Brand")


def _ensure_brand(name, full_name):
    if frappe.db.exists("Brand", name):
        return False
    doc = frappe.new_doc("Brand")
    doc.brand = name
    if frappe.get_meta("Brand").has_field("ec_brand_name"):
        doc.ec_brand_name = full_name
    if frappe.get_meta("Brand").has_field("ec_status"):
        doc.ec_status = "Active"
    doc.insert(ignore_permissions=True)
    return True


def execute():
    try:
        _ensure_field()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p384 tao truong Brand.ec_contract_code")
        return
    made, filled, kept, missing = [], [], [], []
    for name, full in NEW_BRANDS:
        try:
            if _ensure_brand(name, full):
                made.append(name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p384 tao brand %s" % name)
    for name, code in CODES:
        try:
            if not frappe.db.exists("Brand", name):
                missing.append(name)
                continue
            current = (frappe.db.get_value("Brand", name, FIELD) or "").strip()
            if current:
                kept.append("%s=%s" % (name, current))
                continue
            frappe.db.set_value("Brand", name, FIELD, code)
            filled.append("%s=%s" % (name, code))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p384 ma so HD brand %s" % name)
    frappe.log_error(
        "tao brand: %s\ndien ma: %s\ngiu ma da co: %s\nkhong thay brand: %s"
        % (", ".join(made) or "-", ", ".join(filled) or "-", ", ".join(kept) or "-", ", ".join(missing) or "-"),
        "p384_brand_ma_so_hop_dong (bao cao, khong phai loi)")
