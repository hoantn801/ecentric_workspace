# Copyright (c) 2026, eCentric and contributors
"""Creator master KOL/KOC (11/11/2026) - chay khong can bench.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_creators_service.py

Kiem:
  1. Trung CUNG (CCCD / MST / STK, sau chuan hoa) -> chan, bao ten + ma MISA cua ban ghi co san.
  2. Trung MEM (ten bo dau, SDT 84/0, TikTok @/link) -> hoi lai; xac nhan thi tao + ghi chu.
  3. Quyen: PII chi chu ban ghi / EC Finance / SM thay; nguoi khac thay so da che.
  4. Ma MISA: chi Finance; khong gan mot ma cho hai creator.
  5. Sua: nguoi la khong sua duoc; sua thanh CCCD cua nguoi khac bi chan.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))

from ecentric_workspace.approval_center.shared.creators import domain  # noqa: E402
from ecentric_workspace.approval_center.shared.creators.service import (  # noqa: E402
    CreatorError, CreatorPermissionError, CreatorService)


class FakeRepo:
    def __init__(self, rows=None, roles=None):
        self.rows = {r["name"]: dict(r) for r in (rows or [])}
        self.user_roles = roles or {}
        self.inserted = []
        self.updated = []

    def identity_rows(self, exclude=None):
        return [dict(r) for n, r in self.rows.items() if n != exclude]

    def search(self, query, limit):
        q = query.lower()
        return [r for r in self.rows.values() if q in (r.get("supplier_name") or "").lower()][:limit]

    def get(self, name):
        r = self.rows.get(name)
        return dict(r) if r else None

    def insert(self, values):
        name = "SUP-%03d" % (len(self.rows) + 1)
        self.rows[name] = dict(values, name=name, owner="creator@ec")
        self.inserted.append(values)
        return name

    def update(self, name, values):
        self.rows[name].update(values)
        self.updated.append((name, values))
        return name

    def missing_misa(self):
        return [r for r in self.rows.values() if not r.get("ec_cr_misa_code")]

    def misa_owner(self, code, exclude):
        for n, r in self.rows.items():
            if n != exclude and r.get("ec_cr_misa_code") == code:
                return n
        return None

    def roles(self, user):
        return set(self.user_roles.get(user, []))


EXISTING = {"name": "SUP-001", "supplier_name": "Nguyễn Thị Hảo", "ec_cr_type": "Cá nhân",
            "ec_cr_cccd": "079 123 456 789", "tax_id": "", "ec_bank_account_no": "0011 2233",
            "ec_phone": "+84 912 345 678", "ec_cr_tiktok_id": "@haonguyen",
            "ec_cr_misa_code": "KH0001", "owner": "an@ec"}


def svc(roles=None):
    return CreatorService(FakeRepo([EXISTING], roles or {"ke.toan@ec": ["EC Finance"]}))


def payload(**kw):
    base = {"supplier_name": "Trần Văn B", "ec_cr_type": "Cá nhân", "ec_cr_cccd": "001099000111"}
    base.update(kw)
    return base


class DuplicateTests(unittest.TestCase):
    def test_trung_cccd_sau_chuan_hoa_bi_chan(self):
        with self.assertRaises(CreatorError) as cm:
            svc().create("b@ec", payload(ec_cr_cccd="079123456789"))
        self.assertIn("KH0001", str(cm.exception))
        self.assertIn("CCCD", str(cm.exception))

    def test_trung_so_tai_khoan_bi_chan(self):
        with self.assertRaises(CreatorError):
            svc().create("b@ec", payload(ec_bank_account_no="00112233"))

    def test_trung_ten_bo_dau_thi_hoi_lai_khong_tao(self):
        s = svc()
        out = s.create("b@ec", payload(supplier_name="nguyen thi  hao"))
        self.assertTrue(out["needs_confirm"])
        self.assertEqual(out["matches"][0]["name"], "SUP-001")
        self.assertEqual(s.repo.inserted, [])

    def test_trung_sdt_84_va_tiktok_link(self):
        out = svc().create("b@ec", payload(ec_phone="0912345678"))
        self.assertTrue(out["needs_confirm"])
        out = svc().create("b@ec", payload(ec_cr_tiktok_id="https://www.tiktok.com/@HaoNguyen"))
        self.assertTrue(out["needs_confirm"])

    def test_xac_nhan_thi_tao_va_ghi_chu(self):
        s = svc()
        out = s.create("b@ec", payload(supplier_name="Nguyễn Thị Hảo"), confirm_soft=True)
        self.assertFalse(out["needs_confirm"])
        row = s.repo.inserted[0]
        self.assertEqual(row["supplier_group"], domain.CREATOR_GROUP)
        self.assertEqual(row["supplier_type"], "Individual")
        self.assertIn("Nguyễn Thị Hảo", row["ec_cr_dup_ack"])

    def test_khong_trung_thi_tao_ngay(self):
        s = svc()
        out = s.create("b@ec", payload())
        self.assertFalse(out["needs_confirm"])
        self.assertIsNone(s.repo.inserted[0]["ec_cr_dup_ack"])

    def test_ma_misa_khong_nhan_tu_nguoi_tao(self):
        s = svc()
        s.create("b@ec", payload(ec_cr_misa_code="HACK"))
        self.assertNotIn("ec_cr_misa_code", s.repo.inserted[0])


class ValidationTests(unittest.TestCase):
    def test_ca_nhan_phai_co_cccd(self):
        with self.assertRaises(CreatorError):
            svc().create("b@ec", payload(ec_cr_cccd=""))

    def test_cong_ty_phai_co_mst(self):
        with self.assertRaises(CreatorError):
            svc().create("b@ec", {"supplier_name": "Cty A", "ec_cr_type": "Công ty"})

    def test_cccd_sai_do_dai(self):
        with self.assertRaises(CreatorError):
            svc().create("b@ec", payload(ec_cr_cccd="12345"))

    def test_loai_la(self):
        with self.assertRaises(CreatorError):
            svc().create("b@ec", payload(ec_cr_type="KOL"))


class PermissionTests(unittest.TestCase):
    def test_nguoi_la_thay_so_da_che(self):
        view = svc().get("la@ec", "SUP-001")
        self.assertFalse(view["can_see_pii"])
        self.assertTrue(view["ec_cr_cccd"].endswith("6789"))
        self.assertNotIn("079", view["ec_cr_cccd"])
        self.assertNotIn("ec_cr_dob", view)

    def test_chu_ban_ghi_va_ke_toan_thay_day_du(self):
        self.assertTrue(svc().get("an@ec", "SUP-001")["can_see_pii"])
        self.assertEqual(svc().get("ke.toan@ec", "SUP-001")["ec_cr_cccd"], "079 123 456 789")

    def test_luu_cccd_stk_sdt_da_chuan_hoa(self):
        s = svc()
        s.create("b@ec", payload(ec_cr_cccd="001 099 000 111", ec_phone="+84 98 765 4321",
                                 ec_bank_account_no="1903-4455-66"))
        row = s.repo.inserted[0]
        self.assertEqual((row["ec_cr_cccd"], row["ec_phone"], row["ec_bank_account_no"]),
                         ("001099000111", "0987654321", "1903445566"))

    def test_tim_kiem_khong_bao_gio_tra_pii_day_du(self):
        rows = svc().search("ke.toan@ec", "hảo")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["can_see_pii"])

    def test_nguoi_la_khong_sua_duoc(self):
        with self.assertRaises(CreatorPermissionError):
            svc().update("la@ec", "SUP-001", {"ec_phone": "0900000000"})

    def test_sua_thanh_cccd_nguoi_khac_bi_chan(self):
        s = svc()
        other = s.create("b@ec", payload())["name"]
        with self.assertRaises(CreatorError):
            s.update("creator@ec", other, {"ec_cr_cccd": "079123456789"})

    def test_chu_ban_ghi_sua_duoc(self):
        s = svc()
        s.update("an@ec", "SUP-001", {"ec_phone": "0900000000"})
        self.assertEqual(s.repo.rows["SUP-001"]["ec_phone"], "0900000000")


class MisaTests(unittest.TestCase):
    def test_chi_ke_toan(self):
        with self.assertRaises(CreatorPermissionError):
            svc().missing_misa("an@ec")
        with self.assertRaises(CreatorPermissionError):
            svc().set_misa_code("an@ec", "SUP-001", "KH9")

    def test_danh_sach_chua_co_ma(self):
        s = svc()
        new = s.create("b@ec", payload())["name"]
        self.assertEqual([r["name"] for r in s.missing_misa("ke.toan@ec")], [new])
        self.assertEqual(domain.public_view(s.repo.get(new), False)["misa_label"],
                         domain.MISA_PENDING_LABEL)

    def test_khong_gan_mot_ma_cho_hai_creator(self):
        s = svc()
        new = s.create("b@ec", payload())["name"]
        with self.assertRaises(CreatorError):
            s.set_misa_code("ke.toan@ec", new, "KH0001")
        s.set_misa_code("ke.toan@ec", new, " KH0002 ")
        self.assertEqual(s.repo.rows[new]["ec_cr_misa_code"], "KH0002")


class FixtureTests(unittest.TestCase):
    """Moi truong ma service doc/ghi phai co trong fixtures VA trong bo loc hooks - thieu mot
    ben thi `bench export-fixtures` xoa field hoac site moi thieu field trong im lang."""

    def test_truong_service_dung_deu_co_fixture_va_hooks(self):
        import json
        app = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
        with open(os.path.join(app, "fixtures", "custom_field.json"), encoding="utf-8") as fh:
            fixture = {r["name"] for r in json.load(fh) if r.get("dt") == "Supplier"}
        with open(os.path.join(app, "hooks.py"), encoding="utf-8") as fh:
            hooks = fh.read()
        native = {"name", "supplier_name", "tax_id", "supplier_group", "supplier_type", "owner",
                  "creation", "disabled"}
        used = (set(domain.PUBLIC_FIELDS) | set(domain.WRITABLE_FIELDS) | set(domain.HARD_KEYS)
                | set(domain.SOFT_KEYS) | {"ec_cr_type", "ec_cr_misa_code", "ec_cr_dup_ack"})
        for field in sorted(used - native):
            self.assertIn("Supplier-" + field, fixture, field)
            self.assertIn('"Supplier-%s"' % field, hooks, field)

    def test_pii_o_permlevel_1(self):
        import json
        app = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
        with open(os.path.join(app, "fixtures", "custom_field.json"), encoding="utf-8") as fh:
            rows = {r["fieldname"]: r for r in json.load(fh) if r.get("dt") == "Supplier"}
        for field in domain.PII_FIELDS:
            if field == "ec_bank_account_no":   # field cu cua form PO, giu nguyen permlevel 0
                continue
            self.assertEqual(rows[field].get("permlevel"), 1, field)


if __name__ == "__main__":
    unittest.main()
