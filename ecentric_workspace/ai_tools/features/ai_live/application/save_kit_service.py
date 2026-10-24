# Copyright (c) 2026, eCentric and contributors
"""Luu nhap Bo live: thong tin chung + SP (ma Shopee/TikTok) + FAQ cap brand + cau chung (che do Tiet kiem)."""
import os

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan

_HOST = __import__("re").compile(r"^[A-Za-z0-9_.-]{1,96}$")


class SaveKitService:
    def __init__(self, kits=None, files=None):
        self.kits = kits or _deps.kits()
        self.files = files or _deps.files()

    def execute(self, user, roles, name, payload):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        d = payload if isinstance(payload, dict) else (_common.parse_json(payload, "Bộ live") or {})
        old = self.kits.get(name) if name else None
        if name and not old:
            raise C.AiLiveError(C.KitMsg.NOT_FOUND % name)
        if old and old.get("status") in (C.KitStatus.SENDING, C.KitStatus.BUILDING):
            raise C.AiLiveError(C.KitMsg.BUSY)
        brand = str(d.get("brand") or "").strip()
        if not C.BRAND_RE.match(brand):
            raise C.AiLiveError(C.KitMsg.NEED_BRAND if not brand else C.Msg.BAD_BRAND % brand)
        host = str(d.get("host_key") or "").strip()
        if host and not _HOST.match(host):
            raise C.AiLiveError(C.KitMsg.BAD_HOST)
        mode = d.get("mode") or "full"
        if mode not in C.MODES:
            raise C.AiLiveError(C.Msg.BAD_MODE)
        try:
            brk = int(d.get("break_sec") or C.DEFAULT_BREAK_SEC)
        except (TypeError, ValueError):
            brk = 0
        if brk not in C.BREAK_SECS:
            raise C.AiLiveError(C.Msg.BAD_BREAK)
        products = kit_plan.normalize_products(d.get("products"))
        faq = kit_plan.normalize_faq(d.get("faq"))
        generic = kit_plan.normalize_generic(d.get("generic"))
        bg = str(d.get("background") or "") or None
        if bg and os.path.splitext(bg)[1].lower() not in C.BG_EXT:
            raise C.AiLiveError("Nền phải là video mp4/webm/mov hoặc ảnh png/jpg/webp.")
        urls = [a["file"] for _, a in kit_plan.audio_entries(products, faq, generic)] + ([bg] if bg else [])
        allowed = set()
        if old:
            allowed = {a["file"] for _, a in kit_plan.audio_entries(old.get("products") or [], old.get("faq") or [],
                                                                   old.get("generic") or {})} | {old.get("background")}
        _deps.check_files(self.files, user, roles, urls, allowed)
        values = {"brand": brand, "title": str(d.get("title") or "").strip()[:140] or brand, "host_key": host,
                  "voice_id": str(d.get("voice_id") or "").strip()[:80], "voice_provider": str(d.get("voice_provider") or "")[:40],
                  "mode": mode, "break_sec": str(brk), "background": bg, "bake_bg": 1 if d.get("bake_bg") else 0,
                  "products": products, "faq": faq, "generic": generic}
        if not old:
            values["status"] = C.KitStatus.DRAFT
        name = self.kits.save(name, values)
        return {"name": name, "summary": kit_plan.summary(products, faq, generic)}
