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
