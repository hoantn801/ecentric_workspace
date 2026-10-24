# Copyright (c) 2026, eCentric and contributors
"""Kiem tra truong cua EC AI Live Brand Config / EC AI Live Machine khi luu (khong goi DB)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


def validate_brand(doc):
    brand = str(doc.brand or "").strip()
    if not C.BRAND_RE.match(brand):
        raise C.AiLiveError(C.Msg.BAD_BRAND % brand)
    doc.brand = brand
    doc.mode = doc.mode or "full"
    if doc.mode not in C.MODES:
        raise C.AiLiveError(C.Msg.BAD_MODE)
    try:
        sec = int(doc.break_sec or C.DEFAULT_BREAK_SEC)
    except (TypeError, ValueError):
        sec = 0
    if sec not in C.BREAK_SECS:
        raise C.AiLiveError(C.Msg.BAD_BREAK)
    doc.break_sec = str(sec)
    if doc.gpu_url:
        doc.gpu_url = str(doc.gpu_url).strip().rstrip("/")
    if float(doc.daily_cost_cap_usd or 0) < 0:
        doc.daily_cost_cap_usd = 0
    for key, field in C.SETTING_FIELDS.items():
        _common.parse_json(doc.get(field), key)


def validate_machine(doc):
    code = str(doc.machine_code or "").strip()
    if not C.MACHINE_RE.match(code):
        raise C.AiLiveError(C.Msg.BAD_MACHINE)
    doc.machine_code = code
    doc.brands = "\n".join(_common.machine_brands({"brands": doc.brands}))
