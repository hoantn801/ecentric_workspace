# Copyright (c) 2026, eCentric and contributors
"""Nap lai bo quiz "Claude buoi 1" tu seed (13/11/2026 sang): them 2 cau ghim tren anh, cau binh
chon len dau, bat power-up. Can patch rieng vi p003 co the da chay o lan deploy truoc (patch chi
chay mot lan). Logic giong het p003."""


def execute():
    from ecentric_workspace.dao_tao.patches import p003_cap_nhat_quiz_claude_buoi1
    p003_cap_nhat_quiz_claude_buoi1.execute()
