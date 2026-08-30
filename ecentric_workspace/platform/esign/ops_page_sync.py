# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho trang "Chân ký cần can thiệp".

Trang nay do REPO so huu hoan toan - khong ai sua no tren site - nen khong dung khoa chong
troi (`expect_sha`) nhu cac trang nghiep vu. Moi lan sync la dung lai tu nguon.

Quyen xem: trang duoc publish, nhung endpoint `ops_inbox` va moi hanh dong deu tu goi
`assert_system_manager`. Nguoi khac mo trang chi thay mot dong bao thieu quyen - khong co
du lieu nao ro ri qua HTML vi HTML khong chua du lieu, no nap qua API.
"""
import os

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "ec-esign/ops"
NAME = "ec-esign-ops"
TITLE = "Chân ký cần can thiệp"

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


def _html():
    """Noi dung trang. Doc hong thi NEM LOI, khong tra chuoi rong.

    page_sync cua Payment Request nuot OSError va tra "" - va dung cai do da tung dong bo
    len site mot trang THIEU HAN panel ky so, ma sync van bao thanh cong (21/08). Mot trang
    quan tri rong ma bao "da dong bo" con te hon mot lan sync that bai.
    """
    with open(os.path.join(_UI_DIR, "ops_page.html"), encoding="utf-8") as fh:
        html = fh.read()
    if "ec-esign-ops-script" not in html:
        raise ValueError("ops_page.html thieu phan script - khong dong bo mot trang hong")
    return html


def sync():
    return page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, _html(), publish=1)
