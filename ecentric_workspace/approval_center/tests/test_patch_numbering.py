# Copyright (c) 2026, eCentric and contributors
"""Chặn TÁI DIỄN việc trùng số patch. Chạy độc lập, không cần bench:
    python3 ecentric_workspace/approval_center/tests/test_patch_numbering.py

Vì sao không đổi tên 6 patch trùng cũ (p034/p035/p036): Frappe khoá patch theo ĐƯỜNG DẪN
module đầy đủ, nên đổi tên = patch mới = CHẠY LẠI trên production. Sáu patch đó đều gọi
page_sync.sync() nên chạy lại gần như vô hại, nhưng "gần như" không phải "chắc chắn", còn
lợi ích chỉ là log dễ đọc. Đã chạy rồi thì để nguyên; việc đáng làm là không đẻ thêm cái mới.

Test này khoá danh sách trùng ĐÃ BIẾT: thêm số trùng mới -> đỏ ngay.
"""
import os
import re
import sys
from collections import defaultdict

# Trùng số có sẵn từ trước, đã chạy trên prod — chấp nhận, không đổi tên.
KNOWN_DUPLICATES = {
    "034": {"p034_create_employee_info_update_page", "p034_create_purchase_request_page"},
    "035": {"p035_create_livestream_supplies_page", "p035_create_payment_request_page"},
    "036": {"p036_create_budget_setting_page", "p036_create_service_referral_page"},
    # 2026-08-27: p085_resync_hub_todo_tab đổi tên thành p092 để tránh trùng p085 khác,
    # nhưng lúc đó nhánh payment_request cũng đang dùng p092 -> lại trùng. Cả hai ĐÃ chạy
    # trên prod (Patch Log 17:42 và 19:45 cùng ngày) nên để nguyên. Bài học: trước khi đặt
    # số patch, chạy test này để lấy "số cao nhất đang dùng" thay vì đếm mắt.
    "092": {"p092_resync_hub_todo_tab", "p092_resync_payment_request_signing_ux"},
}


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    patch_dir = os.path.join(root, "patches")
    by_number = defaultdict(set)
    for filename in os.listdir(patch_dir):
        m = re.match(r"^(p(\d+))_.+\.py$", filename)
        if m:
            by_number[m.group(2)].add(filename[:-3])

    fails = []
    dupes = {num: names for num, names in by_number.items() if len(names) > 1}

    for num, names in sorted(dupes.items()):
        known = KNOWN_DUPLICATES.get(num)
        if known == names:
            print("PASS - p%s trung nhung la truong hop cu da chap nhan" % num)
        else:
            print("FAIL - p%s bi trung SO MOI: %s" % (num, sorted(names)))
            fails.append(num)

    for num in sorted(KNOWN_DUPLICATES):
        if num not in dupes:
            print("PASS - p%s khong con trung (co the go khoi KNOWN_DUPLICATES)" % num)

    highest = max(int(n) for n in by_number) if by_number else 0
    print("PASS - so patch cao nhat trong nhanh nay: p%03d" % highest)
    print("       LUU Y: so nay chi tinh trong NHANH DANG LAM. Nhanh khac co the da dung")
    print("       so cao hon. Truoc khi dat so patch moi: git fetch origin && "
          "git ls-tree --name-only origin/main -- <patches>/ | tail")

    # patches.txt phải khai đúng những patch có trên đĩa (không thừa, không thiếu dòng)
    with open(os.path.join(root, "..", "patches.txt"), encoding="utf-8") as fh:
        listed = {line.strip().split(".")[-1] for line in fh
                  if line.strip().startswith("ecentric_workspace.approval_center.patches.")}
    on_disk = {name for names in by_number.values() for name in names}
    missing = sorted(on_disk - listed)
    if missing:
        print("FAIL - patch co file nhung KHONG khai trong patches.txt: %s" % missing[:5])
        fails.append("missing")
    else:
        print("PASS - moi patch tren dia deu duoc khai trong patches.txt")
    ghost = sorted(listed - on_disk)
    if ghost:
        print("FAIL - patches.txt khai patch KHONG co file: %s" % ghost[:5])
        fails.append("ghost")
    else:
        print("PASS - patches.txt khong khai patch ma")

    print("SOME_FAIL" if fails else "ALL_PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
