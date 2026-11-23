# Copyright (c) 2026, eCentric and contributors
"""/ky-luat/quyet-dinh?id=<EC Discipline Decision Request> - CEO xem va ky quyet dinh ky luat.
Route cua EC Approval Type DISCIPLINE_DECISION (link thong bao / hub mo thang trang nay)."""
from ecentric_workspace.hr.ky_luat import pages

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render_decision(context)
