# Copyright (c) 2026, eCentric and contributors
"""Dependency mac dinh cho service Giam sat (nap muon de test chay khong can Frappe)."""


def machines():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
    return MachineRepository()


def health():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import HealthRepository
    return HealthRepository()


def samples():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.health_sample_repository import HealthSampleRepository
    return HealthSampleRepository()


def thumbs():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.thumb_repository import ThumbRepository
    return ThumbRepository()


def alerts():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.alert_log_repository import AlertLogRepository
    return AlertLogRepository()


def settings():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.alert_settings_repository import AlertSettingsRepository
    return AlertSettingsRepository()


def sender():
    from ecentric_workspace.ai_tools.features.ai_live.infrastructure import alert_channels
    return alert_channels


def incidents():
    """fix10h: su co may im lang / bao dong gui ho (xac nhan, leo thang)."""
    from ecentric_workspace.ai_tools.features.ai_live.repositories.incident_repository import IncidentRepository
    return IncidentRepository()


def slot_reports():
    """fix10h: ke hoach vs thuc te tung khung (push_slot_report)."""
    from ecentric_workspace.ai_tools.features.ai_live.repositories.slot_report_repository import SlotReportRepository
    return SlotReportRepository()


def costs():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.cost_log_repository import CostLogRepository
    return CostLogRepository()


def brands():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
    return BrandConfigRepository()
