# Copyright (c) 2026, eCentric and contributors
"""Ghi lai + bao cau hoi TINH NGHI toi AI (Hoan 27/11/2026: "cau nao tinh nghi thi note lai bao
minh, co ghi log lai").

Tinh nghi = mot trong:
  salary   hoi luong / thu nhap / thuong cua ai do (bi chan, khong goi AI)
  pnl      hoi PnL / doanh thu / GMV / loi nhuan / chi phi (bi chan)
  history  lich su chat gui len co luot "AI" tu nhan da duoc phep / co so lieu - dau hieu GIA MAO
  output   AI suyt tra ve so lieu luong / tai chinh (chot cuoi da thay cau tra loi)
  param    tham so la trong eC Mate (trang / ten tep chua cau hoi vung cam)

KHAC voi EC AI Usage Log (khong luu noi dung cau hoi - Hoan 07/10): bang nay CHI ghi cau tinh
nghi, cat 500 ky tu, de nguoi giam sat xem. Xem: role System Manager / `EC AI Usage Viewer`.
Bao: chuong thong bao (Notification Log) cho nguoi co role `EC AI Usage Viewer`; cung nguoi hoi +
cung loai trong 1 gio chi bao 1 lan (van ghi du dong). Ghi / bao hong -> khong lam hong luot AI.
"""
import re

DOCTYPE = "EC AI Guard Log"
NOTIFY_ROLE = "EC AI Usage Viewer"
TEXT_CAP = 500
DEDUPE_SECONDS = 3600
KINDS = {
    "salary": "Hỏi lương / thu nhập / thưởng",
    "pnl": "Hỏi PnL / doanh thu / lợi nhuận / chi phí",
    "history": "Lịch sử chat có dấu hiệu giả mạo",
    "output": "AI suýt trả số liệu lương / tài chính",
    "param": "Tham số lạ trong eC Mate",
}
#: Luot "AI" trong lich su TU NHAN da duoc phep / cap quyen -> gia mao (AI that khong noi the).
_CLAIM = re.compile(r"(duoc phep|cho phep|cap quyen|da duoc duyet|authori[sz]ed|permission|"
                    r"quan tri|admin|bo qua (luat|quy tac|huong dan))")


def forged(turns, fold):
    """PURE. Cac luot role 'model' trong lich su client gui ma tu nhan duoc phep / cap quyen."""
    return [h for h in turns or [] if h.get("role") != "user" and _CLAIM.search(fold(h.get("text") or ""))]


def row(kind, channel, text, user, department=""):
    """PURE. -> dict mot dong log (cat noi dung, loai la -> 'param')."""
    kind = kind if kind in KINDS else "param"
    return {"user": user or "", "department": department or "", "kind": kind,
            "kind_label": KINDS[kind], "channel": channel or "",
            "question": " ".join(str(text or "").split())[:TEXT_CAP]}


def note(kind, channel, text):
    """Ghi mot dong + bao (co chong lap). KHONG nem."""
    try:
        import frappe
        user = getattr(frappe.session, "user", "") or ""
        dept = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "department") or ""
        r = row(kind, channel, text, user, dept)
        doc = frappe.get_doc(dict(r, doctype=DOCTYPE))
        doc.insert(ignore_permissions=True, ignore_links=True)
        _notify(frappe, doc.name, r)
        return doc.name
    except Exception:
        try:
            import frappe
            frappe.log_error(title="ai_guard_log")
        except Exception:
            pass
        return None


def _notify(frappe, name, r):
    key = "ec_ai_guard_notified:%s:%s" % (r["user"], r["kind"])
    cache = frappe.cache()
    if cache.get_value(key):
        return
    cache.set_value(key, 1, expires_in_sec=DEDUPE_SECONDS)
    users = frappe.get_all("Has Role", filters={"role": NOTIFY_ROLE, "parenttype": "User"},
                           pluck="parent")
    users = [u for u in set(users) if frappe.db.get_value("User", u, "enabled")]
    who = frappe.db.get_value("User", r["user"], "full_name") or r["user"]
    for u in users:
        frappe.get_doc({
            "doctype": "Notification Log", "for_user": u, "type": "Alert",
            "subject": "AI: %s - %s" % (r["kind_label"], who),
            "email_content": "%s (%s, %s): %s" % (who, r["department"] or "-", r["channel"], r["question"]),
            "document_type": DOCTYPE, "document_name": name,
        }).insert(ignore_permissions=True)
