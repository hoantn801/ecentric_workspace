# Copyright (c) 2026, eCentric and contributors
"""Hang so cua Chat noi bo (lop gan Raven vao ERP). Khong import frappe."""

#: Trang A (PO chot 05/10/2026): Raven nhung trong vo shell ERP.
ROUTE = "/chat"
#: App Raven (The Commit Company). Module nay KHONG sua gi cua Raven, chi goi API cong khai
#: cua no duoi phien nguoi dung - quyen kenh rieng / DM do chinh Raven loc.
RAVEN_APP = "raven"
RAVEN_BASE = "/raven"
RAVEN_ROLE = "Raven User"

#: site_config. Bat = an bieu tuong tin nhan tren thanh tren + trang /chat bao "tam tat".
#: Khong can deploy; trang da cache HTML thi can xoa cache website.
KILL_SWITCH = "ec_chat_disabled"

#: So cuoc tro chuyen toi da trong khay tha xuong (C).
INBOX_LIMIT = 8
#: Do dai doan xem truoc tin cuoi (ky tu).
PREVIEW_LEN = 90

#: Ten loai tin khong phai van ban -> nhan thay the.
MESSAGE_TYPE_LABELS = {
    "Image": "[Ảnh]",
    "File": "[Tệp]",
    "Poll": "[Bình chọn]",
}

MSG_NO_ACCESS = ("Tài khoản của bạn chưa được bật Chat nội bộ. "
                 "Nhờ HR hoặc IT cấp quyền \"Raven User\" rồi tải lại trang.")
MSG_DISABLED = "Chat nội bộ đang tạm tắt."
MSG_NOT_INSTALLED = "Chat nội bộ chưa được cài trên hệ thống."
MSG_LOAD_FAILED = "Không tải được tin nhắn. Thử lại sau ít phút."
