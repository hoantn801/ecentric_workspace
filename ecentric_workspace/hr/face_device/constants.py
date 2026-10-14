# Copyright (c) 2026, eCentric and contributors
"""Hang so cho may cham cong khuon mat Hikvision (ec-face-checkin-v1)."""

# --- site_config.json (Frappe Cloud > Site > Site Config). Khong commit secret. ---
CONF_PUSH_TOKEN = "ec_face_push_token"        # may tu day (HTTP Listening): ?k=<token>
CONF_SYNC_TOKEN = "ec_face_sync_token"        # nut dong bo tren laptop CnB: header
CONF_DISABLED = "ec_face_checkin_disabled"    # 1 = nhan request nhung khong ghi gi
CONF_RUN_AS = "ec_face_run_as"                # ban ghi duoc tao duoi ten user nay
CONF_PASS_MINORS = "ec_face_pass_minors"      # ghi de danh sach ma "xac thuc thanh cong"

TOKEN_HEADER = "X-EC-Face-Token"
DEFAULT_RUN_AS = "Administrator"

# Ma su kien ISAPI. major 5 = su kien (Event). minor = loai su kien con:
#   1  (0x01) the hop le          38 (0x26) van tay khop
#   75 (0x4b) khuon mat khop
# Chi nhung lan XAC THUC THANH CONG moi la mot lan cham cong. Mo cua tu xa,
# nguoi la, quet sai... deu la major 5 nhung KHONG phai cham cong.
MAJOR_EVENT = 5
DEFAULT_PASS_MINORS = (1, 38, 75)

# Cung gia tri mac dinh voi Server Script ec_hr_checkin.
DEFAULT_SHIFT = "EC Standard 9-18"
DEFAULT_CUTOFF = "10:00:00"

DEVICE_PREFIX = "HIK"
MAX_EVENTS_PER_CALL = 1000
MAX_BODY_BYTES = 2 * 1024 * 1024

LOG_IN = "IN"
LOG_OUT = "OUT"

DT_EMPLOYEE = "Employee"
DT_CHECKIN = "Employee Checkin"
DT_ATTENDANCE = "Attendance"
DT_SHIFT = "Shift Type"
DT_TS_CLOSE = "EC Timesheet Close"
TS_CLOSED_STATES = ("Member Closed", "Closed")
EMPLOYEE_SERIES = "HR-EMP-"
EMPLOYEE_DIGITS = 5
