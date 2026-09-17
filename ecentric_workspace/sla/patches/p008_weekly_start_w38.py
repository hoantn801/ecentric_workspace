# Copyright (c) 2026, eCentric and contributors
"""Nhom Bao cao tuan: doi ngay bat dau tinh tu 21/09 -> TUAN NAY (2026-W38).

Chu so huu doi chot chieu 17/09: "weekly report tinh tu tuan nay di, tinh tu mai
18.9 luon".

VI SAO GHI 12/09 CHU KHONG PHAI 18/09 - doc ky truoc khi sua dong nay.

`effective_from` duoc doi chieu voi `opened_at` cua nghia vu, va voi nhom bao cao
tuan thi `opened_at` la `creation` cua ban ghi `Weekly Team Update` - tuc la luc
bo sinh hang ngay TAO ra o bao cao, khong phai han nop.

Do tren ban chay 17/09:

    2026-W37   71 ban   tao 05/09 -> 09/09   han 11/09 18:00
    2026-W38   74 ban   tao 12/09 -> 16/09   han 18/09 18:00   <- tuan nay

Ghi 18/09 thi moi ban cua W38 (tao 12-16/09) deu roi vao "truoc ngay ap dung" va
TUAN NAY BI BO QUA - dung nguoc lai dieu chu so huu muon. 12/09 la ngay ban W38
dau tien duoc tao, nen no bat tron W38 va khong cham vao W37 (ban cuoi cua W37
tao 09/09). Khoang 10-11/09 khong co ban nao, nen moc nay khong mo ho.

DIEU PHAI NOI TRUOC VOI CHU SO HUU: luc chot, 72/74 ban cua W38 con o `Draft` va
han la 18:00 ngay mai. Bat nhom nay tu tuan nay nghia la phan lon cong ty se co
mot dong `Missed` cho tuan dau tien, tru khi co mot loi nhac truoc do. Day la
quyet dinh cua chu so huu, khong phai cua patch - patch chi ghi lai rang dieu do
da duoc nhin thay truoc khi bam.

FAIL-SAFE: boc rieng, ghi Error Log, luon ket thuc xanh. Mot patch nem loi la
chan ca ban deploy.
"""
import frappe

from ecentric_workspace.sla.constants import DT_TYPE, TYPE_WEEKLY_REPORT

#: Ngay ban `Weekly Team Update` dau tien cua tuan 2026-W38 duoc tao.
START = "2026-09-12"


def execute():
    try:
        name = frappe.db.get_value(DT_TYPE, {"type_code": TYPE_WEEKLY_REPORT}, "name")
        if not name:
            frappe.log_error(title="p008 ngay bat dau Bao cao tuan",
                             message="khong thay loai nghia vu %s" % TYPE_WEEKLY_REPORT)
            return
        current = frappe.db.get_value(DT_TYPE, name, "effective_from")
        if str(current or "") == START:
            frappe.log_error(title="p008 ngay bat dau Bao cao tuan",
                             message="da dung (%s), khong sua gi" % START)
            return
        frappe.db.set_value(DT_TYPE, name, "effective_from", START)
        frappe.log_error(
            title="p008 ngay bat dau Bao cao tuan",
            message="%s: %s -> %s (bat tron tuan 2026-W38, han 18/09 18:00)"
                    % (TYPE_WEEKLY_REPORT, current or "(trong)", START))
    except Exception:
        frappe.log_error(title="p008 ngay bat dau Bao cao tuan",
                         message=frappe.get_traceback())
