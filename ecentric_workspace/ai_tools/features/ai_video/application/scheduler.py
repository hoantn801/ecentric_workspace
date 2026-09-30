# Copyright (c) 2026, eCentric and contributors
"""Cron 10 phut: day tiep cac du an AI Video dang chay (chay dem). Tat bang site_config
`ec_video_scheduler_disabled: 1`."""
import frappe


def tick():
    if frappe.conf.get("ec_video_scheduler_disabled"):
        return
    from ecentric_workspace.ai_tools.features.ai_video.application import service
    service.tick_all()
