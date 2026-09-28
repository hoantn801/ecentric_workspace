# Copyright (c) 2026, eCentric and contributors
"""Hang so cua trang Tong quan (/tong-quan) - the Nhan su.

Quyen xem KHONG tu dat ra o day: nhom truong nao duoc tra ve do chinh permlevel cua
DocType Employee quyet dinh (Meta.get_permlevel_access). Doi quyen trong Desk thi trang
doi theo, khong co hai nguon su that."""

ROUTE = "tong-quan"

#: Ai thay the "Nhan su" tren trang Tong quan. Chi la cua vao (UX); du lieu van loc
#: theo permlevel o tung truong.
HR_CARD_ROLES = ("System Manager", "HR Manager", "HR User", "EC CnB")

EMPLOYEE = "Employee"
CONTRACT = "EC Employee Contract"
DEPARTMENT = "Department"
SSA = "Salary Structure Assignment"
SALARY_SLIP = "Salary Slip"

ACTIVE = "Active"
MANAGEMENT_DEPT = "Management - EC"
DEPT_SUFFIX = " - EC"
HEAD_GRADES = ("Trưởng phòng", "BOD")
PROBATION = "Thử việc"
INTERN = "Thực tập"

CONTRACT_WARN_DAYS = 30
PROBATION_WARN_DAYS = 14

#: permlevel 0 - danh ba, moi nguoi co the xem trang deu nhan.
L0_FIELDS = ("name", "employee_name", "employee_number", "status", "department",
             "ec_sub_department", "designation", "grade", "reports_to", "employment_type",
             "date_of_joining", "relieving_date", "company_email", "user_id", "gender")
#: permlevel 2 - thong tin noi bo HR (laptop, thang tang BHXH, hop dong).
L2_FIELDS = ("ec_laptop", "ec_thang_tang_bhxh")
#: permlevel 1 - thong tin ca nhan. Chi HR Manager / EC CnB (theo DocPerm hien hanh).
L1_FIELDS = ("date_of_birth", "cell_number", "personal_email", "passport_number",
             "date_of_issue", "place_of_issue", "permanent_address", "current_address",
             "ec_bien_so_xe", "bank_name", "bank_ac_no", "health_insurance_no",
             "ec_ma_kcb", "ec_noi_kcb")

#: Kiem "ho so thieu du lieu": (truong, nhan hien thi, permlevel can co de kiem).
#: Nguoi khong co permlevel do thi khong kiem - khong lo ca viec "co hay khong co" du lieu.
REQUIRED_CHECKS = (
    ("reports_to", "Người quản lý", 0),
    ("user_id", "Tài khoản đăng nhập", 0),
    ("designation", "Chức danh", 0),
    ("grade", "Chức vụ", 0),
    ("cell_number", "SĐT", 1),
    ("date_of_birth", "Ngày sinh", 1),
    ("passport_number", "CCCD", 1),
    ("bank_ac_no", "Số TK ngân hàng", 1),
    ("health_insurance_no", "Mã BHXH", 1),
)
#: BOD khong co nguoi quan ly - khong tinh la thieu.
NO_MANAGER_GRADES = ("BOD",)

#: Truong ca nhan chi hien 4 so cuoi tren trang (du nguoi xem co quyen): tranh lo qua vai.
MASKED_FIELDS = ("passport_number", "bank_ac_no")

MSG_UNKNOWN = "Không tải được dữ liệu. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."
MSG_FORBIDDEN = "Bạn không có quyền xem mục này."
