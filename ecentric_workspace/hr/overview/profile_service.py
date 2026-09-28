# Copyright (c) 2026, eCentric and contributors
"""Ho so mot nhan vien cho khung ben phai (tab Danh sach). Thuan Python.

Moi nhom chi co mat khi nguoi xem co permlevel tuong ung. So CCCD / so tai khoan chi
hien 4 so cuoi - sua / xem day du thi mo ho so trong ERP (Desk van kiem quyen).
KHONG co luong."""
from ecentric_workspace.hr.overview import constants as C
from ecentric_workspace.hr.overview.service import dept_label, missing_labels

ORG_LABELS = (
    ("employee_number", "Mã NV"), ("department", "Phòng"), ("ec_sub_department", "Sub"),
    ("designation", "Chức danh"), ("grade", "Chức vụ"), ("manager", "Quản lý"),
    ("employment_type", "Loại hình"), ("date_of_joining", "Ngày vào"),
    ("company_email", "Email công ty"), ("gender", "Giới tính"),
)
HR_LABELS = (("ec_laptop", "Laptop"), ("ec_thang_tang_bhxh", "Tháng tăng BHXH"))
PERSONAL_LABELS = (
    ("date_of_birth", "Ngày sinh"), ("cell_number", "SĐT"), ("personal_email", "Email cá nhân"),
    ("passport_number", "CCCD"), ("date_of_issue", "Ngày cấp"), ("place_of_issue", "Nơi cấp"),
    ("permanent_address", "Thường trú"), ("current_address", "Tạm trú"),
    ("bank_name", "Ngân hàng"), ("bank_ac_no", "Số TK"), ("health_insurance_no", "Mã BHXH"),
    ("ec_ma_kcb", "Mã KCB"), ("ec_noi_kcb", "Nơi KCB"), ("ec_bien_so_xe", "Biển số xe"),
)


def mask(value):
    s = str(value or "")
    return ("•••• " + s[-4:]) if len(s) > 4 else ("••••" if s else "")


def _pairs(emp, labels):
    out = []
    for field, label in labels:
        if field not in emp and field != "manager":
            continue          # truong khong doc duoc (permlevel / mask): khong hien ca nhan
        val = emp.get(field)
        if field in C.MASKED_FIELDS:
            val = mask(val)
        elif field == "department":
            val = dept_label(val)
        out.append({"label": label, "value": str(val)[:10] if field.startswith("date") and val else (val or "")})
    return out


class GetHrProfileService:
    def execute(self, emp, contract_rows, levels, manager_name=""):
        levels = set(levels or [0])
        emp = dict(emp, manager=manager_name)
        data = {
            "name": emp["name"], "employee_name": emp.get("employee_name") or emp["name"],
            "headline": " › ".join(x for x in (dept_label(emp.get("department")),
                                                emp.get("ec_sub_department")) if x),
            "erp_url": "/app/employee/" + emp["name"],
            "org": _pairs(emp, ORG_LABELS),
            "missing": missing_labels(emp, levels),
        }
        if 2 in levels:
            data["hr"] = _pairs(emp, HR_LABELS)
            data["contracts"] = [{
                "type": c.get("loai_hop_dong") or "", "no": c.get("so_hop_dong") or "",
                "from": str(c.get("tu_ngay") or "")[:10], "to": str(c.get("den_ngay") or "")[:10],
                "no_term": bool(c.get("khong_thoi_han")),
            } for c in contract_rows]
        if 1 in levels:
            data["personal"] = _pairs(emp, PERSONAL_LABELS)
        return data
