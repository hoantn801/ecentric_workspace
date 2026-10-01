# Copyright (c) 2026, eCentric and contributors
"""Trang thai HIEU LUC cua khao sat - tinh theo gio, khong luu.

Cot `status` chi giu y dinh cua nguoi tao (Nhap / Da phat hanh / Da dong). "Dang mo" hay
"Sap mo" hay "Het han" thi tinh moi lan doc tu open_at / close_at / gioi han so phieu. Nho
vay khong can job dinh ky de dong khao sat dung gio: qua gio la dong, ngay lap tuc, o moi
cho doc.
"""
from ecentric_workspace.surveys import constants as C


def effective_status(status, open_at, close_at, now, responses=0, limit=0):
    """open_at / close_at / now: datetime hoac None (so sanh duoc voi nhau)."""
    if status == C.STATUS_DRAFT:
        return C.EFFECTIVE_DRAFT
    if status != C.STATUS_OPEN:
        return C.EFFECTIVE_CLOSED
    if close_at and now >= close_at:
        return C.EFFECTIVE_CLOSED
    if limit and responses >= limit:
        return C.EFFECTIVE_CLOSED
    if open_at and now < open_at:
        return C.EFFECTIVE_SCHEDULED
    return C.EFFECTIVE_OPEN


def can_edit_questions(status):
    """Sua cau hoi sau khi da co nguoi tra loi van duoc (nhu Google Forms), nhung trinh soan
    canh bao. Chi cam khi da DONG han de ket qua cuoi cung khong doi duoi chan nguoi doc."""
    return status != C.STATUS_CLOSED
