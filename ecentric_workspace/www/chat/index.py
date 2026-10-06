# Copyright (c) 2026, eCentric and contributors
"""/chat - Chat noi bo: Raven nhung trong vo shell ERP. Logic o chat/pages.py.

    ?c=<ma kenh>   mo thang kenh / DM do (tu khay tin nhan tren thanh tren). Chi mo duoc kenh
                   co trong danh sach Raven tra cho chinh nguoi nay; sai -> trang dau Raven.
"""
from ecentric_workspace.chat import pages

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.get_context(context)
