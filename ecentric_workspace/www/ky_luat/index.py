# Copyright (c) 2026, eCentric and contributors
"""/ky-luat - Ky luat lao dong: the vang (nhac nho noi bo) + ho so ky luat the do / den.

Route: hooks.website_route_rules /ky-luat -> ky_luat. Tham so: ?tab=the-vang|ho-so, ?ma=<ten> mo
popup chi tiet. Quyen xem tung dong do hr/ky_luat/application/access.py quyet dinh."""
from ecentric_workspace.hr.ky_luat import pages

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render_index(context)
