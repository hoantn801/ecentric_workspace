# Copyright (c) 2026, eCentric and contributors
"""Hang so cua module Khao sat - KHONG import frappe.

Moi ten DocType / role / trang thai / loai cau hoi dung o service, controller, patch va
test deu lay tu day. Ma loai cau hoi va ma trang thai duoc ghi thang vao DB (form_json,
cot status) va duoc ca JS doc lai, nen go sai o mot cho la mot loai cau hoi "khong ai
nhan" - phai sua o DUNG MOT cho.
"""

# --------------------------------------------------------------------------- DocType --
SURVEY = "EC Survey"
TARGET = "EC Survey Target"
EDITOR = "EC Survey Editor"
PRIZE = "EC Survey Prize"
RESPONSE = "EC Survey Response"
PARTICIPANT = "EC Survey Participant"

EMPLOYEE = "Employee"
DEPARTMENT = "Department"

# ------------------------------------------------------------------------------ Role --
#: Duoc TAO khao sat. Ai can thi HR / admin gan role nay (patch chi tao role rong).
ROLE_CREATOR = "EC Survey Creator"
#: Cac role cung duoc tao khao sat ma khong can gan them.
CREATOR_ROLES = (ROLE_CREATOR, "HR Manager", "System Manager")
#: Xem + quan ly MOI khao sat (khong chi cua minh).
ADMIN_ROLES = ("System Manager",)

# ------------------------------------------------------------------------ Trang thai --
STATUS_DRAFT = "Draft"
STATUS_OPEN = "Open"
STATUS_CLOSED = "Closed"
STATUSES = (STATUS_DRAFT, STATUS_OPEN, STATUS_CLOSED)

#: Trang thai HIEU LUC (tinh theo gio, khong luu) - JS doc dung cac chuoi nay.
EFFECTIVE_DRAFT = "draft"
EFFECTIVE_SCHEDULED = "scheduled"      # da phat hanh, chua toi gio mo
EFFECTIVE_OPEN = "open"
EFFECTIVE_CLOSED = "closed"

# --------------------------------------------------------------------------- Doi tuong --
AUDIENCE_ALL = "all"                   # moi nhan vien Active
AUDIENCE_CUSTOM = "custom"             # theo phong ban / nguoi duoc chon
AUDIENCE_MODES = (AUDIENCE_ALL, AUDIENCE_CUSTOM)

TARGET_DEPARTMENT = "Department"
TARGET_USER = "User"
TARGET_EXCLUDE = "Exclude"
TARGET_KINDS = (TARGET_DEPARTMENT, TARGET_USER, TARGET_EXCLUDE)

# -------------------------------------------------------------------------- Phan thuong --
REWARD_NONE = "none"
REWARD_WHEEL = "wheel"                 # vong quay - ket qua ngay sau khi nop
REWARD_NUMBER = "lucky_number"         # con so may man - tu chon so, quay theo gio hen
REWARD_RACE = "race"                   # dua ve dich - ai nop cung co xe, chay theo gio hen
REWARD_MODES = (REWARD_NONE, REWARD_WHEEL, REWARD_NUMBER, REWARD_RACE)
#: Kieu quay THEO GIO HEN: bao truoc, popup trang chu tu chay, ket qua giu ca ngay.
SCHEDULED_MODES = (REWARD_NUMBER, REWARD_RACE)

#: Lich quay (PO 01/10): bao + popup truoc 5 phut, "dang quay" 3 phut, ket qua hien toi het ngay.
DRAW_NOTIFY_BEFORE_MIN = 5
DRAW_LIVE_MIN = 3
#: Bo qua bao truoc neu job tre qua muc nay (site sap / scheduler tat) - bao muon vo nghia.
DRAW_NOTIFY_LATE_MIN = 10
#: "Luot quay tiep theo" trong popup: lich trong 30 ngay toi; o popup hien khi co luot trong 7 ngay.
DRAW_UPCOMING_DAYS = 30
DRAW_TILE_DAYS = 7
DRAW_UPCOMING_MAX = 8
#: Dai so may man 1..N.
NUMBER_RANGE_DEFAULT = 100
NUMBER_RANGE_MIN = 10
NUMBER_RANGE_MAX = 9999
#: Toi da so lan hien trong cuoc dua (xe con lai gom vao "va N xe khac").
RACE_LANES = 12
REALTIME_DRAW = "ec_survey_draw"

DRAW_COUNTDOWN = "countdown"
DRAW_LIVE = "live"
DRAW_DONE = "done"

RESULT_NONE = ""
RESULT_WIN = "Win"
RESULT_LOSE = "Lose"

# ----------------------------------------------------------------------- Loai cau hoi --
Q_SHORT = "short_text"
Q_PARAGRAPH = "paragraph"
Q_SINGLE = "single"                    # trac nghiem (chon 1)
Q_MULTI = "multi"                      # hop kiem (chon nhieu)
Q_DROPDOWN = "dropdown"
Q_SCALE = "scale"                      # thang tuyen tinh (vd 1-5, 0-10 / NPS)
Q_RATING = "rating"                    # sao
Q_GRID_SINGLE = "grid_single"          # luoi trac nghiem
Q_GRID_MULTI = "grid_multi"            # luoi hop kiem
Q_RANKING = "ranking"                  # xep hang (kieu MS Forms)
Q_DATE = "date"
Q_TIME = "time"
Q_FILE = "file"

QUESTION_TYPES = (Q_SHORT, Q_PARAGRAPH, Q_SINGLE, Q_MULTI, Q_DROPDOWN, Q_SCALE, Q_RATING,
                  Q_GRID_SINGLE, Q_GRID_MULTI, Q_RANKING, Q_DATE, Q_TIME, Q_FILE)
CHOICE_TYPES = (Q_SINGLE, Q_MULTI, Q_DROPDOWN)
OPTION_TYPES = CHOICE_TYPES + (Q_RANKING,)
GRID_TYPES = (Q_GRID_SINGLE, Q_GRID_MULTI)
#: Loai co the re nhanh "chuyen toi phan..." theo lua chon (giong Google Forms).
BRANCH_TYPES = (Q_SINGLE, Q_DROPDOWN)
#: Loai cham diem duoc o che do bai kiem tra.
QUIZ_TYPES = (Q_SHORT, Q_SINGLE, Q_MULTI, Q_DROPDOWN)

KIND_QUESTION = "question"
KIND_SECTION = "section"               # ngat phan (trang moi)
KIND_NOTE = "note"                     # khoi tieu de + mo ta, khong co cau tra loi
ITEM_KINDS = (KIND_QUESTION, KIND_SECTION, KIND_NOTE)

GOTO_NEXT = ""                         # sang phan ke tiep
GOTO_SUBMIT = "__submit__"             # nop luon

VALIDATION_NONE = "none"
VALIDATION_NUMBER = "number"
VALIDATION_EMAIL = "email"
VALIDATION_PHONE = "phone"
VALIDATION_LENGTH = "length"
VALIDATIONS = (VALIDATION_NONE, VALIDATION_NUMBER, VALIDATION_EMAIL, VALIDATION_PHONE,
               VALIDATION_LENGTH)

# ---------------------------------------------------------------------------- Gioi han --
MAX_ITEMS = 200
MAX_OPTIONS = 60
MAX_GRID_ROWS = 30
MAX_TEXT = 300                         # tieu de cau hoi / lua chon
MAX_DESC = 3000                        # mo ta
MAX_ANSWER = 5000                      # cau tra loi doan van
MAX_SHORT_ANSWER = 500
MAX_FILES = 5
MAX_PRIZES = 20
SCALE_MIN_LOW, SCALE_MAX_HIGH = 0, 10
RATING_MAX = 10
TEXT_SAMPLES = 200                     # so cau tra loi chu hien o trang ket qua

# ------------------------------------------------------------------------------ Trang --
ROUTE_HUB = "khao-sat"
ROUTE_FILL = "khao-sat/lam"
ROUTE_MANAGE = "khao-sat/quan-ly"
ROUTE_BUILDER = "khao-sat/soan"


def fill_url(name):
    return "/%s?s=%s" % (ROUTE_FILL, name)
