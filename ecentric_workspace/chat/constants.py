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

#: 06/10/2026 - lop "ruot" cho Raven (khong sua Raven): trang /raven (ca khi nhung trong /chat)
#: duoc chen them, LUC TRA RESPONSE, mot <link> CSS mau ERP + mot <script src> nho noi ban dich
#: tieng Viet (boot) vao ham dich cua Raven. Bat = tat CA HAI (Raven ve nguyen ban tieng Anh).
#: Khong can deploy.
SKIN_KILL_SWITCH = "ec_chat_skin_disabled"
#: Bang dich Raven (chuoi giao dien web cua Raven 3.0.0 -> tieng Viet), canh file nay.
RAVEN_VI_FILE = "raven_vi.json"
#: Tep tinh (public/) chen vao trang /raven.
SKIN_CSS = "public/css/ec_chat_raven_skin.css"
RAVEN_BOOT_JS = "public/js/ec_raven_boot.js"

#: 07/10/2026 - "Phieu trong chat" (PO: "moi nguoi co the gui phieu qua lai trong chat cho tien").
#:   * Dan link phieu ERP vao chat -> tin nhan mang the phieu (link_doctype/link_document cua Raven).
#:   * The phieu mo trang duyet ERP (/approvals/...) thay vi Desk (hook raven_document_link_override).
#:   * Bot nhan rieng moi thong bao phe duyet (cung luc chuong ERP), kem the phieu.
#: Tat bot: site_config ec_chat_bot_disabled. Tat ca 3: ec_chat_phieu_disabled. Khong can deploy.
PHIEU_KILL_SWITCH = "ec_chat_phieu_disabled"
BOT_KILL_SWITCH = "ec_chat_bot_disabled"
#: Ten Raven Bot (cung la ten hien trong chat). Tao tu dong lan gui dau.
BOT_NAME = "Phiếu duyệt"
BOT_DESCRIPTION = "Báo phiếu cần duyệt và kết quả duyệt từ ERP eCentric."
BOT_IMAGE = "/files/eCentric%20logo%20-%20mini.png"
#: event_type cua notification_center duoc bot gui sang chat. approval_required gom ca
#: "Can duyet", "Da duyet", "Bi tu choi", "Can bo sung", "Da huy" (transitions.notify).
BOT_EVENT_TYPES = ("approval_required",)
#: Ten mien ERP chap nhan khi doc link dan vao chat (ngoai get_url() cua site).
ERP_HOSTS = ("team.ecentric.vn", "ecentric-new.s.frappe.cloud")
