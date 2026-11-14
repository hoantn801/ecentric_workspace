# Copyright (c) 2026, eCentric and contributors
"""p366_dao_tao_quiz_trang: dua 7 trang Dao tao + Quiz truc tiep len site (Hoan 12/11/2026).

/dao-tao, /dao-tao/bai, /dao-tao/quan-ly, /quiz, /quiz/soan, /quiz/choi, /quiz/chieu - repo so
huu toan bo byte (dao_tao/pages/*). Trang nao dang chiem route ma khong phai cua module thi
duoc doi sang `<route>-cu`, khong xoa (dao_tao/pages/sync.py). Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p366 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p366_dao_tao_quiz_trang")
