# Copyright (c) 2026, eCentric and contributors
"""Mot ban `Weekly Team Update` dan toi nghia vu SLA nao. Thuan - khong import frappe.

Tach ra khoi `infrastructure/weekly_source.py` de kiem chung duoc bang `python3`
tran. Phan quyet dinh o day nho nhung no la cho de sai nhat: mot ban bao cao bi
xep nham thanh "chua nop" se cham `Missed` cho mot nguoi da nop that.
"""

TERMINAL_STATES = ("Submitted", "Reviewed")

ACT_SKIP = "skip"
ACT_OPEN = "open"
ACT_CLOSE = "close"


def decide(row, terminal_states=TERMINAL_STATES):
    """row -> (hanh_dong, moc_dong, ly_do).

    `row` la dict co: submitter, due_at, status, submitted_at, modified.

    Ba luat, va luat dau quan trong nhat:

      * khong co nguoi nop hoac khong co han -> BO QUA, kem ly do. Khong co han
        thi khong cham diem duoc, va doan bua mot con han se cham tre cho nguoi
        khong he co nghia vu. Ly do duoc tra ve de ben goi dem va bao cao, chu
        khong nuot im lang: gan nhu luon la phong ban do thieu `Department
        Reporting Window`.
      * trang thai ket thuc -> DONG, moc dong lay `submitted_at`.
      * con lai -> MO.
    """
    if not row.get("submitter"):
        return ACT_SKIP, None, "khong co nguoi nop"
    if not row.get("due_at"):
        return ACT_SKIP, None, "khong co han"
    if (row.get("status") or "") in terminal_states:
        # `submitted_at` co the trong voi ban duoc nop truoc khi truong do ton
        # tai. Luc do `modified` la xap xi tot nhat - lech vai giay den vai phut
        # so voi luc nop, nhung van dung phia so voi han. Bo qua ca ban ghi thi
        # nguoi da nop bien mat khoi mau so, tuc la duoc mien phi.
        return ACT_CLOSE, (row.get("submitted_at") or row.get("modified")), "da nop"
    return ACT_OPEN, None, "dang mo"
