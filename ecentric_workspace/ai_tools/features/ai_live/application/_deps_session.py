# Copyright (c) 2026, eCentric and contributors
"""Dependency mac dinh cho service Phien live / Lich live (nap muon de test chay khong can Frappe)."""


def sessions():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.session_repository import SessionRepository
    return SessionRepository()


def commands():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.command_repository import CommandRepository
    return CommandRepository()


def machines_all():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
    return MachineRepository()


def logs():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.session_log_repository import SessionLogRepository
    return SessionLogRepository()


def races():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.race_repository import RaceRepository
    return RaceRepository()
