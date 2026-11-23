# Copyright (c) 2026, eCentric and contributors
"""Hang so module Ky luat (Dot 3 quy trinh nhan su, Hoan chot 22-23/11/2026) - KHONG import frappe.

Hai doi tuong, hai cach xu ly (HR_REVIEW_OPUS_2026-11-22.md muc 7):
  * The vang (EC HR Notice): nhac nho NOI BO, ngoai engine duyet. Khong tru luong (D127), khong
    la can cu tai pham phap ly, KHONG tu gop thanh the do.
  * The do / the den (EC Discipline Case): ho so vu viec 4 buoc theo BLLD 2019 + ND 145/2020.
    Engine duyet chi dung cho buoc CEO ky quyet dinh (approval feature discipline_decision).

So ngay / so thang ghi o day la LUAT (D122, D123, D126) - khong phai cau hinh. SLA noi bo
(han phan hoi the vang, so ngay bao truoc hop...) doc tu EC Discipline Settings, gia tri o day
chi la mac dinh khi Settings chua co.

KHONG CO TRUONG TIEN NAO trong module nay (D127 cam phat tien thay ky luat) - test khoa.
"""

# --------------------------------------------------------------------------- DocType --
NOTICE = "EC HR Notice"                 # the vang
CASE = "EC Discipline Case"             # the do / den
RULE = "EC Discipline Rule"             # danh muc dieu khoan noi quy
SETTINGS = "EC Discipline Settings"     # Single
LOG = "EC Discipline Log"               # bang con nhat ky (dung cho ca NOTICE va CASE)
DECISION = "EC Discipline Decision Request"   # phieu engine (approval_center)
EMPLOYEE = "Employee"
LEAVE_APPLICATION = "Leave Application"
EC_LEAVE_REQUEST = "EC Leave Request"

# ------------------------------------------------------------------------------ Role --
#: CnB / HR (brief: role EC CnB + role HR; HR Manager / HR User la role chuan cua HRMS).
HR_ROLES = ("EC CnB", "HR", "HR Manager", "HR User")
CEO_ROLES = ("EC CEO",)
ADMIN_ROLES = ("System Manager",)
#: Xem MOI the vang / ho so (khong gioi han team).
ALL_VIEW_ROLES = HR_ROLES + CEO_ROLES + ADMIN_ROLES
DEFAULT_SIGNER_ROLE = "EC CEO"

# ---------------------------------------------------------------------- The vang --
NOTICE_PENDING = "Chờ phản hồi"
NOTICE_READ = "Đã đọc"
NOTICE_REPLIED = "Đã phản hồi"
NOTICE_NO_REPLY = "Không phản hồi"
NOTICE_CANCELLED = "Đã huỷ"
NOTICE_STATUSES = (NOTICE_PENDING, NOTICE_READ, NOTICE_REPLIED, NOTICE_NO_REPLY, NOTICE_CANCELLED)
NOTICE_AUTO_TEXT = "Đã thông báo, nhân viên không phản hồi"
ISSUER_LM = "Quản lý trực tiếp"
ISSUER_HR = "HR"

# ------------------------------------------------------------------- The do / den --
CARD_RED = "Thẻ đỏ"
CARD_BLACK = "Thẻ đen"
CARDS = (CARD_RED, CARD_BLACK)

P_REPRIMAND = "Khiển trách"
P_EXTEND = "Kéo dài thời hạn nâng lương"
P_DEMOTE = "Cách chức"
P_DISMISS = "Sa thải"
PENALTIES = (P_REPRIMAND, P_EXTEND, P_DEMOTE, P_DISMISS)
#: The nao duoc chon hinh thuc nao (brief: do = khien trach; den = keo dai / cach chuc / sa thai).
CARD_PENALTIES = {CARD_RED: (P_REPRIMAND,), CARD_BLACK: (P_EXTEND, P_DEMOTE, P_DISMISS)}
MAX_EXTEND_MONTHS = 6                    # D124: keo dai thoi han nang luong khong qua 6 thang

#: Can cu sa thai D125 BLLD 2019 - ma so ghi vao DB, nhan hien tren form.
DISMISS_GROUNDS = (
    ("1", "Trộm cắp, tham ô, đánh bạc, cố ý gây thương tích, sử dụng ma tuý tại nơi làm việc"),
    ("2", "Tiết lộ bí mật kinh doanh, bí mật công nghệ, xâm phạm quyền sở hữu trí tuệ, có hành vi "
          "gây thiệt hại nghiêm trọng hoặc đe doạ gây thiệt hại đặc biệt nghiêm trọng về tài sản, "
          "lợi ích của công ty; quấy rối tình dục tại nơi làm việc được quy định trong nội quy"),
    ("3", "Tái phạm khi đang bị kéo dài thời hạn nâng lương hoặc cách chức mà chưa được xoá kỷ luật"),
    ("4", "Tự ý bỏ việc 05 ngày cộng dồn trong 30 ngày hoặc 20 ngày cộng dồn trong 365 ngày "
          "mà không có lý do chính đáng"),
)
DISMISS_GROUND_CODES = tuple(c for c, _l in DISMISS_GROUNDS)
GROUND_RECIDIVISM = "3"
#: Hinh thuc lam can cu "tai pham" cho can cu (3) - CHUA duoc xoa.
RECIDIVISM_BASE_PENALTIES = (P_EXTEND, P_DEMOTE)

# Trang thai ho so (thu tu thu tuc)
S_PROPOSED = "Đề xuất"              # LM de xuat - HR tham dinh
S_DRAFT = "Đang lập"                # HR lap ho so + bien ban vi pham
S_POSTPONED = "Hoãn"                # vuong thoi gian khong duoc xu ly (D122.4)
S_NOTIFIED = "Đã thông báo họp"
S_MET = "Đã họp"
S_AT_CEO = "Trình CEO"
S_ISSUED = "Đã ban hành"
S_NO_DISCIPLINE = "Không kỷ luật"
S_EXPIRED = "Hết thời hiệu"
S_EXPUNGED = "Đã xoá kỷ luật"
S_CANCELLED = "Đã huỷ"
CASE_STATUSES = (S_PROPOSED, S_DRAFT, S_POSTPONED, S_NOTIFIED, S_MET, S_AT_CEO, S_ISSUED,
                 S_NO_DISCIPLINE, S_EXPIRED, S_EXPUNGED, S_CANCELLED)
CASE_OPEN = (S_PROPOSED, S_DRAFT, S_POSTPONED, S_NOTIFIED, S_MET, S_AT_CEO)
CASE_CLOSED = (S_ISSUED, S_NO_DISCIPLINE, S_EXPIRED, S_EXPUNGED, S_CANCELLED)
#: NV duoc xem ho so cua chinh minh tu luc da duoc thong bao hop.
CASE_VISIBLE_TO_EMPLOYEE = (S_NOTIFIED, S_MET, S_AT_CEO, S_ISSUED, S_NO_DISCIPLINE, S_EXPUNGED)
#: Ly do hoan (D122.4) - HR tick; nghi phep doc tu Leave Application + EC Leave Request.
BLOCK_LEAVE = "Nghỉ ốm / điều dưỡng / nghỉ được đồng ý"
BLOCK_CUSTODY = "Đang bị tạm giữ, tạm giam"
BLOCK_INVESTIGATION = "Chờ kết luận của cơ quan có thẩm quyền"
BLOCK_MATERNITY = "Nữ mang thai, nghỉ thai sản, nuôi con dưới 12 tháng"
MANUAL_BLOCKS = (BLOCK_CUSTODY, BLOCK_INVESTIGATION, BLOCK_MATERNITY)

ATTEND_UNKNOWN = "Chưa trả lời"
ATTEND_YES = "Sẽ tham dự"
ATTEND_NO = "Không tham dự"
PRESENT_YES = "Có mặt"
PRESENT_NO = "Vắng mặt dù đã được thông báo"
ABSENT_NOTE = ("Nhân viên vắng mặt dù đã được thông báo hợp lệ; cuộc họp vẫn tiến hành. "
               "Việc vắng mặt / im lặng không có nghĩa là đồng ý với nội dung vi phạm.")

# --------------------------------------------------------------------------- Luat --
LIMITATION_MONTHS = 6               # D123.1
LIMITATION_MONTHS_FINANCE = 12      # D123.1: lien quan tai chinh, tai san, bi mat
EXTENSION_DAYS = 60                 # D123.2
#: D126: xoa ky luat (thang) ke tu ngay bi xu ly neu khong tai pham. Sa thai: khong xoa.
EXPUNGE_MONTHS = {P_REPRIMAND: 3, P_EXTEND: 6, P_DEMOTE: 36}

# ------------------------------------------------------------ SLA mac dinh (Settings) --
DEFAULT_NOTICE_REPLY_DAYS = 3       # the vang: NV phan hoi trong 3 ngay LV
DEFAULT_HR_REVIEW_DAYS = 3          # HR tham dinh de xuat
DEFAULT_MEETING_NOTICE_DAYS = 5     # bao truoc hop >= 5 ngay LV
DEFAULT_CEO_SIGN_DAYS = 2           # CEO ky trong 2 ngay LV sau hop
DEFAULT_LIMITATION_WARN_DAYS = 14   # canh bao con 14 ngay toi het thoi hieu
YELLOW_HINT_COUNT = 3               # goi y HR: 3 the vang ...
YELLOW_HINT_WINDOW_DAYS = 90        # ... trong 90 ngay (chi goi y, khong tu len the do)

LEGAL_NOTE = ("Ghi chú pháp lý: HR/pháp chế xác nhận NĐ 145/2020 nguyên văn trước khi dùng thật. "
              "Không phạt tiền, không cắt lương thay cho kỷ luật (Điều 127 BLLĐ 2019).")
YELLOW_NOTE = ("Thẻ vàng là nhắc nhở nội bộ: không trừ lương, không phải hình thức kỷ luật và không "
               "là căn cứ tái phạm theo luật. Nhiều thẻ vàng không tự chuyển thành thẻ đỏ.")

ROUTE = "/ky-luat"
ROUTE_DECISION = "/ky-luat/quyet-dinh"
