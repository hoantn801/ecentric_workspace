# Copyright (c) 2026, eCentric and contributors
"""Thu anh khuon mat qua ERP cho may cham cong Hikvision (ec-face-photo-v1, 05/11/2026)."""

ROUTE = "/khuon-mat"
HR_ROLES = ("HR Manager", "HR User", "EC CnB", "System Manager")

FILE_PREFIX = "ec_face_"          # File rieng tu gan vao Employee, ten ec_face_<HR-EMP-xxxxx>.jpg
# v2 (05/11): ket qua AI soi anh nam o duoi ten tep (khong them truong). Khong duoi = chua kiem.
SUFFIX_AI_OK = "__ai"             # AI kiem dat (da cat cho mat vao giua)
SUFFIX_REVIEW = "__hrxem"         # AI che nhung nguoi gui xac nhan anh dung -> HR xem lai
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MIN_SIDE = 240                    # anh qua nho -> may khong nhan duoc mat
MAX_SIDE = 720
TARGET_BYTES = 190 * 1024         # iVMS-4200 / may: moi anh JPG <= 200 KB
EMPLOYEE_SERIES = "HR-EMP-"

CONSENT_TEXT = ("Tôi đồng ý để eCentric dùng ảnh khuôn mặt này cho máy chấm công / mở cửa "
                "văn phòng. Ảnh chỉ Nhân sự (HR/CnB) xem được.")
REMIND_EVENT = "task_assigned"
