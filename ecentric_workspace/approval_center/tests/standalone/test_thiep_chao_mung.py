# Copyright (c) 2026, eCentric and contributors
"""Thiep "Chao mung thanh vien moi" (welcome.build_card / card_payload) - 24/11/2026.

Mau HR dang gui (Hoan gui anh 24/11): tieu de, Ten / Vi tri / Bo phan, loi gioi thieu dang trich
dan nghieng, loi keu goi say hi, Welcome on board. Ban moi giu het + quan ly + ngay + nut nhan chao."""
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "features", "new_staff_preparation",
                    "application", "welcome.py")

DB = {("User", "lm@ecentric.vn", "full_name"): "Tuấn Lý",
      ("Department", "Service - EC", "department_name"): "Service"}
EMP = {"HR-EMP-1": {"company_email": "phong.nguyen@ecentric.vn", "user_id": None}}


def _nap():
    f = types.ModuleType("frappe")

    def get_value(dt, name, field, as_dict=False):
        if dt == "Employee":
            return EMP.get(name)
        return DB.get((dt, name, field))

    f.db = types.SimpleNamespace(get_value=get_value, set_value=lambda *a, **k: None,
                                 commit=lambda: None)
    f.log_error = lambda *a, **k: None
    f.conf = {}
    f.session = types.SimpleNamespace(user="a@b")
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: None
    utils.nowdate = lambda: "2026-12-15"
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"], sys.modules["frappe.utils"] = f, utils
    try:
        m = types.ModuleType("welcome_under_test")
        exec(compile(io.open(_SRC, encoding="utf-8").read(), _SRC, "exec"), m.__dict__)
        return m
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class _Row(dict):
    __getattr__ = dict.get


def _row(**kw):
    r = _Row(name="NSP-1", candidate_name="Nguyễn Vũ Duy Phong",
             position="Affiliate Marketing Manager", department="Service - EC",
             welcome_intro="Hi Ecentric's team, I'm Phong.\nHope we'll connect!",
             line_manager="lm@ecentric.vn", new_employee="HR-EMP-1", onboard_date="2026-12-15")
    r.update(kw)
    return r


def _card(m, **kw):
    out = m.build_card(m.card_payload(_row(**kw)))
    json.dumps(out, ensure_ascii=False)          # gui duoc qua webhook
    return out["attachments"][0]["content"]


def _texts(node, acc=None):
    acc = [] if acc is None else acc
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("text", "value", "title") and isinstance(v, str):
                acc.append(v)
            _texts(v, acc)
    elif isinstance(node, list):
        for v in node:
            _texts(v, acc)
    return acc


class TestThiep(unittest.TestCase):
    def setUp(self):
        self.m = _nap()

    def test_du_noi_dung_mau_hr(self):
        t = " | ".join(_texts(_card(self.m)))
        for s in ("Chào mừng thành viên mới", "Nguyễn Vũ Duy Phong", "Affiliate Marketing Manager",
                  "Service", "Đôi lời giới thiệu từ chính chủ", "say hi",
                  "Welcome on board, Nguyễn Vũ Duy Phong!"):
            self.assertIn(s, t)

    def test_ten_khong_viet_hoa_toan_bo(self):
        self.assertNotIn("NGUYỄN VŨ DUY PHONG", " ".join(_texts(_card(self.m))))

    def test_them_quan_ly_va_ngay(self):
        t = " | ".join(_texts(_card(self.m)))
        self.assertIn("Tuấn Lý", t)
        self.assertIn("Thứ Ba, 15/12/2026", t)

    def test_loi_gioi_thieu_nghieng_giu_xuong_dong(self):
        c = _card(self.m)
        runs = _walk(c, "TextRun")
        self.assertEqual([r["text"] for r in runs], ["Hi Ecentric's team, I'm Phong.",
                                                    "Hope we'll connect!"])
        self.assertTrue(all(r["italic"] for r in runs))

    def test_khong_gioi_thieu_thi_khong_khung(self):
        c = _card(self.m, welcome_intro="  ")
        self.assertNotIn("Đôi lời", " ".join(_texts(c)))
        self.assertEqual(_walk(c, "ColumnSet"), [])

    def test_nut_nhan_chao_chi_khi_co_email(self):
        c = _card(self.m)
        self.assertEqual(len(c["actions"]), 1)
        a = c["actions"][0]
        self.assertIn("Nhắn chào Phong", a["title"])
        self.assertTrue(a["url"].startswith("https://teams.microsoft.com/l/chat/0/0?users="
                                            "phong.nguyen%40ecentric.vn&message="))
        self.assertNotIn("actions", _card(self.m, new_employee=None))

    def test_thieu_quan_ly_khong_loi(self):
        t = " ".join(_texts(_card(self.m, line_manager=None)))
        self.assertNotIn("Quản lý:", t)

    def test_khong_lo_luong(self):
        s = json.dumps(_card(self.m), ensure_ascii=False).lower()
        for w in ("salary", "lương", "compensation"):
            self.assertNotIn(w, s)

    def test_job_gui_thiep_ban_day_du(self):
        """send_welcome_teams phai dung card_payload (co quan ly + nut), khong phai payload."""
        posted = []
        self.m.today_rows = lambda day=None: [_row()]
        self.m._post = lambda url, data: posted.append(data) or (202, "")
        self.m.frappe.conf["ec_onboard_welcome_webhook_url"] = "https://example.invalid/hook"
        self.assertEqual(self.m.send_welcome_teams()["sent"], 1)
        c = posted[0]["attachments"][0]["content"]
        self.assertIn("Tuấn Lý", " ".join(_texts(c)))
        self.assertIn("actions", c)

    def test_popup_khong_nhan_them_email(self):
        p = self.m.payload(_row())
        self.assertNotIn("chat_email", p)


def _walk(node, typ, acc=None):
    acc = [] if acc is None else acc
    if isinstance(node, dict):
        if node.get("type") == typ:
            acc.append(node)
        for v in node.values():
            _walk(v, typ, acc)
    elif isinstance(node, list):
        for v in node:
            _walk(v, typ, acc)
    return acc


if __name__ == "__main__":
    unittest.main()
