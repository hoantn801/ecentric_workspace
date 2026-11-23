# Copyright (c) 2026, eCentric and contributors
"""Hang so luat / gioi han cua Host QC. Nguong chinh duoc nam o Host QC Settings + Host QC Rule (ERP la nguon);
o day chi la thu KHONG doi theo van hanh (nhom diem, khuon ma, gioi han kich thuoc)."""
import re

GROUPS = {"A": ("Voice", 30), "B": ("Compliance & Focus", 20), "C": ("Engagement", 25), "D": ("Sales", 25)}
GENERAL_GROUP = "–"                       # muc chung trong bang huong dan, khong tru diem
FORMATS = ("sales", "mega", "kol", "branding", "education")

SESSION_ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
MACHINE_ID_RE = re.compile(r"^[A-Z0-9._-]{1,40}$")
VIOLATION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,140}$")
RULE_CODE_RE = re.compile(r"^[A-Z]{2,8}-\d{2}$")

TOKEN_BYTES = 32                          # token may = 64 ky tu hex
AUTH_FAIL_LIMIT = 30                      # sai 30 lan / 10 phut / IP thi chan
AUTH_FAIL_WINDOW_S = 600
NEXT_SESSION_BEFORE_MIN = 60              # next_session: planned_start trong [now-60', now+30']
NEXT_SESSION_AFTER_MIN = 30
MIC_STALE_MIN = 10                        # mic qua 10' khong thay -> "khong thay tu <gio>"
MAX_MICS = 40
CLIP_MAX_BYTES = 15 * 1024 * 1024
CLIP_TYPES = ("video/mp4",)
TRANSCRIPT_MAX_BYTES = 30 * 1024 * 1024
QUOTE_MAX = 300
TEXT_MAX = 2000
EXCERPT_MAX = 20000
RULES_CACHE_S = 3600

# thoi gian: may gui epoch ms (hoac ISO); ERP luu Datetime theo gio VN
TZ = "Asia/Ho_Chi_Minh"
