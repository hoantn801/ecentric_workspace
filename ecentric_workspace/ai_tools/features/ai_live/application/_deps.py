# Copyright (c) 2026, eCentric and contributors
"""Dependency mac dinh cho service Bo live / Kho host (nap muon de test chay khong can Frappe)."""


def worker():
    from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client
    return worker_client


def kits():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.kit_repository import KitRepository
    return KitRepository()


def files():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.file_repository import FileRepository
    return FileRepository()


def brands():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
    return BrandConfigRepository()


def labels():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.host_label_repository import HostLabelRepository
    return HostLabelRepository()


def check_files(files_repo, user, roles, urls, allowed=()):
    """Chi nhan file do chinh nguoi dung tai len (hoac System Manager), tru file da nam san trong Bo live."""
    from ecentric_workspace.ai_tools.features.ai_live import constants as C
    sm = "System Manager" in (roles or ())
    for u in urls:
        if not u or u in allowed:
            continue
        owner = files_repo.owner(u)
        if owner is None or (owner != user and not sm):
            raise C.AiLiveError(C.KitMsg.BAD_FILE % u)
