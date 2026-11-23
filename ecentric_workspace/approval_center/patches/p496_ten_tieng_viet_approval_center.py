# Copyright (c) 2026, eCentric and contributors
"""p496_ten_tieng_viet_approval_center (23/11/2026, Hoan: "the khong dep nhu mockup - song ngu, chu
thich, mau icon"): dien ten tieng Viet + mo ta ngan cho loai phieu va ten tieng Viet cho nhom.

Chi DIEN khi o con trong (title_vi / name_vi / short_name_vi) - khong de gia tri nguoi da sua.
Mo ta (description): chi dien khi trong hoac la cau tieng Anh khong dau (mo ta mac dinh cu); gia tri
cu ghi vao Error Log de doi chieu. Loai / nhom khong co tren site thi bo qua. Khong xoa, khong doi
approval_title (ten tieng Anh giu lam dong phu va dung o thong bao cu). Khong goi ra ngoai."""
import frappe

# code: (ten tieng Viet, mo ta ngan)
TYPES = {
    "PAYMENT_REQUEST": ("Đề nghị thanh toán", "Thanh toán NCC, KOL/KOC, chi phí vận hành"),
    "PURCHASE_REQUEST": ("Đề nghị mua hàng", "Mua hàng hoá, dịch vụ trước khi thanh toán"),
    "BUDGET_SETTING": ("Thiết lập ngân sách", "Đặt / điều chỉnh ngân sách theo brand"),
    "ANNUAL_BUDGET": ("Ngân sách năm", "Đặt ngân sách cả năm"),
    "MONTHLY_BUDGET": ("Ngân sách tháng", "Đặt ngân sách theo tháng"),
    "AFFILIATE_BONUS_REQUEST": ("Thưởng affiliate", "Thưởng hoa hồng cho affiliate"),
    "CONTRACT_REVIEW": ("Rà soát hợp đồng", "Rà soát, duyệt và ký số hợp đồng"),
    "HR_ACTIVITY": ("Hoạt động nhân sự", "Team building, sự kiện nội bộ"),
    "BRAND_WEIGHT": ("Phân bổ tỷ trọng brand", "Chia % thời gian nhân sự theo brand"),
    "HIRING_REQUEST": ("Đề xuất tuyển dụng", "Mở vị trí tuyển mới hoặc tuyển thay thế"),
    "OFFER_REQUEST": ("Offer ứng viên", "Mở từ phiếu Tuyển dụng đã duyệt"),
    "NEW_STAFF_PREPARATION": ("Chuẩn bị nhân sự mới", "Tự tạo khi Offer duyệt: thiết bị, tài khoản, chỗ ngồi"),
    "PROMOTION_REQUEST": ("Thăng chức / điều chỉnh lương", "Đề xuất thăng chức, đổi chức danh, lương"),
    "LATERAL_MOVE": ("Điều chuyển nội bộ", "Chuyển phòng ban, vị trí ngang cấp"),
    "EMPLOYEE_INFO_UPDATE": ("Cập nhật thông tin nhân sự", "Sửa thông tin hồ sơ: ngân hàng, địa chỉ, MST…"),
    "EMPLOYEE_REVIEW": ("Đánh giá nhân sự", "Đánh giá thử việc, thực tập, hợp đồng"),
    "RESIGNATION": ("Nghỉ việc", "Nộp đơn nghỉ việc; duyệt xong mở Bàn giao"),
    "CLEARANCE_REQUEST": ("Bàn giao nghỉ việc", "Thu hồi tài sản, tài khoản khi nghỉ việc"),
    "DISCIPLINE_DECISION": ("Quyết định kỷ luật", None),
    "DOCUMENT_REQUEST": ("Xin giấy tờ", "Xác nhận công tác, giấy tờ nhân sự"),
    "ASSET_DAMAGE_LOSS": ("Báo hỏng / mất tài sản", "Báo tài sản công ty hư hỏng hoặc thất lạc"),
    "ASSET_REQUEST": ("Cấp phát tài sản", "Xin laptop, màn hình, thiết bị làm việc"),
    "AI_TOPUP": ("Nạp credit công cụ AI", "Nạp credit ChatGPT, Claude, công cụ AI"),
    "DATA_REQUEST": ("Yêu cầu dữ liệu", "Đã chuyển sang Trung tâm Dữ liệu"),
    "SYSTEM_REQUEST": ("Yêu cầu hệ thống", "Cấp tài khoản, phân quyền hệ thống"),
    "DAILY_TARGET": ("Đặt target ngày", "Đặt target doanh số ngày theo brand"),
    "DAILY_TARGET_PROJECT": ("Target ngày theo dự án", "Đặt target ngày cấp dự án"),
    "BOOKING_REQUEST": ("Đặt booking KOL/KOC", "Đặt lịch booking KOL/KOC"),
    "OUTSIDE_WORK": ("Làm việc bên ngoài", "Gặp khách, công tác ngoài văn phòng"),
    "LEAVE_REQUEST": ("Nghỉ phép", "Nghỉ phép năm, nghỉ ốm, việc riêng"),
    "LATE_EARLY_OUT": ("Đi muộn / về sớm", "Xin đi muộn, về sớm"),
    "COMPENSATION_LEAVE": ("Nghỉ bù", "Nghỉ bù cho ngày làm thêm"),
    "SPECIAL_BONUS": ("Thưởng đặc biệt", "Đề xuất thưởng ngoài chính sách"),
    "ADHOC_APPROVAL": ("Phê duyệt đột xuất", "Gửi thẳng CEO duyệt, thay cho duyệt qua mail"),
    "SERVICE_REFERRAL": ("Giới thiệu dịch vụ", "Giới thiệu khách hàng / dịch vụ"),
    "EMPLOYEE_REFERRAL": ("Giới thiệu ứng viên", "Giới thiệu người quen ứng tuyển"),
    "LIVESTREAM_SAMPLE": ("Nhận hàng mẫu livestream", "Nhận sản phẩm mẫu cho livestream"),
    "LIVESTREAM_SUPPLIES": ("Mượn đồ livestream", "Mượn thiết bị, đạo cụ livestream"),
}
# code: (ten day du, ten ngan tren nut loc)
CATEGORIES = {
    "FINANCE_BUDGET": ("Tài chính & Ngân sách", "Tài chính"),
    "HR": ("Nhân sự", "Nhân sự"),
    "PROCUREMENT_ASSET": ("Mua sắm & Tài sản", "Mua sắm"),
    "IT_DATA": ("CNTT & Dữ liệu", "CNTT & Dữ liệu"),
    "OPERATIONS_PERFORMANCE": ("Vận hành & Hiệu suất", "Vận hành"),
    "ATTENDANCE_WORKPLACE": ("Chấm công & Nơi làm việc", "Chấm công"),
    "ADMINISTRATION": ("Hành chính", "Hành chính"),
    "OTHERS": ("Khác", "Khác"),
}


def _english_default(text):
    t = (text or "").strip()
    return not t or all(ord(ch) < 128 for ch in t)


def execute():
    ket = []
    try:
        if frappe.db.has_column("EC Approval Category", "name_vi"):
            for code, (full, short) in CATEGORIES.items():
                row = frappe.db.get_value("EC Approval Category", code, ["name_vi", "short_name_vi"], as_dict=True)
                if not row:
                    continue
                upd = {}
                if not row.name_vi:
                    upd["name_vi"] = full
                if not row.short_name_vi:
                    upd["short_name_vi"] = short
                if upd:
                    frappe.db.set_value("EC Approval Category", code, upd, update_modified=False)
                    ket.append("cat %s %s" % (code, sorted(upd)))
        if frappe.db.has_column("EC Approval Type", "title_vi"):
            for code, (vi, desc) in TYPES.items():
                row = frappe.db.get_value("EC Approval Type", code, ["title_vi", "description"], as_dict=True)
                if not row:
                    continue
                upd = {}
                if not row.title_vi:
                    upd["title_vi"] = vi
                if desc and _english_default(row.description) and (row.description or "") != desc:
                    upd["description"] = desc
                    if row.description:
                        ket.append("type %s description cu: %s" % (code, row.description[:120]))
                if upd:
                    frappe.db.set_value("EC Approval Type", code, upd, update_modified=False)
                    ket.append("type %s %s" % (code, sorted(upd)))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p496 ten tieng viet approval center", message="\n".join(ket) or "khong doi gi")
