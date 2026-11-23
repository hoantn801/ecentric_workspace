# Copyright (c) 2026, eCentric and contributors
"""Host QC dot 1: tao role Host QC Manager / Viewer, dien mac dinh Host QC Settings, nap bang huong dan
(13 ma loi gom SAL-04 thu nghiem + muc chung) tu seeds/host_qc_rules.json (sinh tu src/rules/defaults.js app 0.1.1).

Idempotent, KHONG ghi de: ma da co (Production da sua) giu nguyen; Settings chi dien o con trong.
Loi tung ma ghi Error Log, khong lam hong migrate."""
import json
import os

import frappe

from ecentric_workspace.host_qc.constants import roles as R
from ecentric_workspace.host_qc.repositories.rule_repository import RuleRepository
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository
from ecentric_workspace.host_qc.services.bump_rules_version_service import BumpRulesVersionService

SEED = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seeds", "host_qc_rules.json")
SETTINGS_DEFAULTS = {
    "llm_models": "gemini-3-8-flash\ngemini-3-8-flash-openai\ngrok-4-7", "claude_model": "claude-haiku-4-5",
    "llm_window_s": 60, "deduction_minor": 3, "deduction_major": 10, "deduction_critical": 18,
    "green_min": 85, "yellow_min": 70, "yellow_minor_count": 5, "red_major_count": 2,
    "alert_minor_at": 5, "alert_major_at": 2, "machine_offline_after_s": 180,
    "evidence_before_s": 15, "evidence_after_s": 15, "evidence_max_s": 30, "evidence_height": 480,
    "evidence_bitrate_k": 1000, "clip_keep_days": 30, "sharepoint_root_folder": "HostQC",
}


def execute():
    for role in (R.MANAGER, R.VIEWER):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
    SettingsRepository().set_defaults(SETTINGS_DEFAULTS)
    seed_rules(RuleRepository(), _load())
    if not SettingsRepository().get().get("rules_version"):
        BumpRulesVersionService().execute()


def _load():
    with open(SEED, encoding="utf-8") as f:
        return json.load(f)["rules"]


def seed_rules(repo, rows):
    added = 0
    for row in rows:
        try:
            if repo.exists(row["code"]):
                continue
            repo.insert(row)
            added += 1
        except Exception:
            frappe.log_error(title="host_qc p001 seed %s" % row.get("code"))
    return added
