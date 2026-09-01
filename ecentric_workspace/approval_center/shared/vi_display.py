# Copyright (c) 2026, eCentric and contributors
"""Việt hoá giá trị hiển thị của Approval Center — CHỈ ở tầng hiển thị.

Giá trị lưu trong DB giữ nguyên tiếng Anh. Đổi option của DocType sẽ làm mọi bản ghi cũ
thành không hợp lệ, phá bộ lọc/báo cáo/tích hợp và cần một cuộc migrate dữ liệu; dịch lúc
đọc ra thì không đụng gì tới dữ liệu và lùi lại được bằng một dòng.

Hai tầng tra cứu:
  BY_FIELD  — khi cùng một chữ tiếng Anh mang nghĩa khác nhau tuỳ form
              (vd "New"/"Existing": loại hợp đồng ≠ tài khoản mới/cũ).
  GLOBAL    — chữ chỉ có một nghĩa trong toàn hệ.

KHÔNG dịch: tên phòng ban (là khoá dữ liệu), thang điểm 1-5, mã mức độ I0/U1,
chuỗi vốn đã song ngữ ("Purchase / Mua vào (EC)"), và chuỗi vốn đã tiếng Việt.
"""

LEVEL_NAMES = {
    "CEO Review": "CEO duyệt",
    "Careers Review": "Careers duyệt",
    "CnB Review": "C&B duyệt",
    "Commercial Manager Review": "Commercial Manager duyệt",
    "Current Direct Manager Review": "Quản lý hiện tại duyệt",
    "Data Review": "Data duyệt",
    "Department Manager Review": "Trưởng phòng duyệt",
    "Department Owner Review": "Phòng ban phụ trách duyệt",
    "Direct Manager": "Quản lý trực tiếp",
    "Direct Manager Review": "Quản lý trực tiếp duyệt",
    "Finance Review": "Finance duyệt",
    "Finance Team Review": "Finance Team duyệt",
    "HOF Review": "Head of Finance duyệt",
    "Head of Finance Review": "Head of Finance duyệt",
    "HR Manager Review": "HR Manager duyệt",
    "HR Review": "HR duyệt",
    "New Line Manager Review": "Quản lý mới duyệt",
    "Operation Review": "Operation duyệt",
    "Referral Review": "Xét giới thiệu",
}

BY_FIELD = {
    "request_kind": {"New": "Hợp đồng / phụ lục mới", "Existing": "Hợp đồng sẵn có"},
    "account_mode": {"New Account": "Tài khoản mới", "Existing Account": "Tài khoản sẵn có"},
    "supplier_mode": {"New supplier": "Nhà cung cấp mới", "Existing supplier": "Nhà cung cấp sẵn có"},
    "request_scope": {"Project level": "Theo dự án", "Consolidated / Total": "Tổng hợp"},
}

GLOBAL = {
    # chung
    "Yes": "Có", "No": "Không", "Maybe": "Có thể", "Unknown": "Chưa rõ", "Other": "Khác",
    "Custom": "Tuỳ chỉnh", "Not Applicable": "Không áp dụng",
    "Included": "Có bao gồm", "Excluded": "Không bao gồm",
    "Low": "Thấp", "Normal": "Bình thường", "High": "Cao", "Urgent": "Khẩn",
    "Myself": "Bản thân", "Requester": "Người yêu cầu",
    # tài sản / vật tư
    "Request new asset": "Xin cấp tài sản mới",
    "Return old asset": "Trả tài sản cũ",
    "Replacement of damaged or obsolete asset": "Thay tài sản hỏng hoặc cũ",
    "Additional asset for current use": "Bổ sung tài sản đang dùng",
    "Request supplies": "Xin cấp vật tư", "Return supplies": "Trả vật tư",
    "Mobile phone": "Điện thoại", "Desktop computer": "Máy tính để bàn",
    "Mobile device": "Thiết bị di động", "Laptop Allowance": "Phụ cấp laptop",
    "Damage": "Hỏng hóc", "Loss": "Mất mát", "Theft": "Bị lấy cắp",
    "Unsuitable environment": "Môi trường không phù hợp",
    # mục tiêu
    "Setting new target": "Đặt mục tiêu mới",
    "Revising current target": "Điều chỉnh mục tiêu hiện tại",
    # hệ thống / dữ liệu
    "Access, permission": "Cấp quyền truy cập",
    "License, account": "Bản quyền, tài khoản",
    "Initiative, solution": "Sáng kiến, giải pháp",
    "Data accuracy, visualization, retrieval": "Độ chính xác, trực quan hoá, truy xuất dữ liệu",
    "Historical data crawling": "Thu thập dữ liệu lịch sử",
    "Data training": "Đào tạo dữ liệu", "New BI report": "Báo cáo BI mới",
    # nghỉ phép
    "Annual": "Phép năm", "Sick": "Nghỉ ốm", "Marriage": "Kết hôn",
    "Maternity": "Thai sản", "Paternity": "Nghỉ vợ sinh", "Bereavement": "Tang chế",
    "Business trip": "Công tác", "Medical checkup": "Khám sức khoẻ",
    "Errand": "Việc vặt", "Company trip": "Du lịch công ty",
    "Personal Matters (Family, Myself,...)": "Việc cá nhân (gia đình, bản thân...)",
    "Have another direction": "Có định hướng khác",
    # thanh toán
    "Pay in advance 100%": "Trả trước 100%",
    "Pay within 7 days": "Trả trong 7 ngày",
    "Pay within 14 days": "Trả trong 14 ngày",
    "Pay within 30 days": "Trả trong 30 ngày",
    # vòng đời / tần suất
    "Create": "Tạo mới", "Modify": "Chỉnh sửa", "Recall": "Thu hồi",
    "Renewal": "Gia hạn", "Replace": "Thay thế", "Upgrade": "Nâng cấp",
    "Top-up": "Nạp thêm", "New Subscription": "Đăng ký mới", "One-time": "Một lần",
    "Monthly": "Hàng tháng", "Quarterly": "Hàng quý",
    "Semi-annual": "Nửa năm", "Double day": "Ngày đôi",
    # nhân sự / giới thiệu
    "New employee": "Nhân viên mới", "Former colleague": "Đồng nghiệp cũ",
    "Friend": "Bạn bè", "Relative": "Người thân", "Freelancer": "Cộng tác viên",
    "Intern": "Thực tập sinh", "Full-time": "Toàn thời gian",
    "Client onboarding": "Nhận khách hàng mới", "Client offboarding": "Kết thúc khách hàng",
    "Offboarding": "Nghỉ việc", "Request for the others": "Yêu cầu hộ người khác",
    # hoạt động
    "Holiday and anniversary": "Lễ và kỷ niệm", "Year-end party": "Tiệc cuối năm",
    "Quarterly team bonding": "Gắn kết đội nhóm hàng quý",
    "Monthly L&D": "Đào tạo hàng tháng", "Cultural Environment": "Môi trường văn hoá",
    "Key live": "Phiên live chính",
}


def level_name(value):
    """Tên cấp duyệt — dùng cho stepper và cột 'Cấp hiện tại'."""
    if not value:
        return value
    return LEVEL_NAMES.get(str(value).strip(), value)


def value(raw, fieldname=None):
    """Giá trị Select. Tra theo trường trước (khử nhập nhằng), rồi tới bảng chung.
    Không khớp thì trả nguyên văn — không bao giờ làm mất dữ liệu hiển thị."""
    if raw is None or raw == "":
        return raw
    text = str(raw).strip()
    if fieldname:
        by_field = BY_FIELD.get(fieldname)
        if by_field and text in by_field:
            return by_field[text]
    return GLOBAL.get(text, raw)
