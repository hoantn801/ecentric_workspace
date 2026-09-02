# Copyright (c) 2026, eCentric and contributors
"""Việt hoá giá trị hiển thị — chạy độc lập:
    python3 ecentric_workspace/approval_center/tests/test_vi_display.py
Khoá 3 tính chất: (1) chỉ dịch khi khớp CHÍNH XÁC, (2) khử nhập nhằng theo tên trường,
(3) KHÔNG dịch những thứ là khoá dữ liệu / mã kỹ thuật / vốn đã song ngữ.
"""
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
spec = importlib.util.spec_from_file_location(
    "vi_display", os.path.join(ROOT, "ecentric_workspace", "approval_center", "shared", "vi_display.py"))
vi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vi)

fails = []


def chk(name, cond):
    print(("PASS" if cond else "FAIL") + " - " + name)
    if not cond:
        fails.append(name)


chk("dich gia tri thuong gap", vi.value("Return old asset") == "Trả tài sản cũ"
    and vi.value("Urgent") == "Khẩn" and vi.value("Yes") == "Có")
chk("dich ten cap duyet", vi.level_name("Direct Manager Review") == "Quản lý trực tiếp duyệt"
    and vi.level_name("CEO Review") == "CEO duyệt")
# khử nhập nhằng
chk("'New' chi dich khi o truong request_kind",
    vi.value("New", "request_kind") == "Hợp đồng / phụ lục mới" and vi.value("New") == "New")
chk("'Existing' theo tung truong khac nhau",
    vi.value("Existing", "request_kind") == "Hợp đồng sẵn có"
    and vi.value("Existing Account", "account_mode") == "Tài khoản sẵn có")
# không dịch nhầm
chk("KHONG dich ten phong ban (la khoa du lieu)",
    vi.value("Human Resources") == "Human Resources" and vi.value("Production") == "Production")
chk("KHONG dich chuoi da song ngu",
    vi.value("Purchase / Mua vào (EC)") == "Purchase / Mua vào (EC)")
chk("KHONG dich ma ky thuat / thang diem",
    vi.value("U0: as soon as possible").startswith("U0")
    and vi.value("3 (Neutral)") == "3 (Neutral)" and vi.value("SCTS") == "SCTS")
chk("gia tri la khong khop -> giu nguyen van", vi.value("Chuỗi bất kỳ") == "Chuỗi bất kỳ")
chk("rong/None -> tra nguyen", vi.value(None) is None and vi.value("") == "" and vi.level_name(None) is None)
chk("khong dich nham chuoi con (chi khop chinh xac)",
    vi.value("Return old asset urgently") == "Return old asset urgently")
# bản dịch không được trùng nhau gây khó hiểu ở stepper
vals = list(vi.LEVEL_NAMES.values())
dupes = {v for v in vals if vals.count(v) > 1}
chk("ban dich ten cap trung nhau chi o cap dong nghia (HOF/Head of Finance)",
    dupes <= {"Head of Finance duyệt"})

print("SOME_FAIL" if fails else "ALL_PASS")
sys.exit(1 if fails else 0)
