# Copyright (c) 2026, eCentric and contributors
"""PO 27/11/2026: mot creator CONG TY / HO KINH DOANH quan ly nhieu KOL / kenh. Creator co danh sach KOL
(bang con EC Creator KOL tren Supplier); hop dong chon mot hay nhieu KOL, MOT tong tien chung.

  * creators.domain: lam sach danh sach (bo dong trong, khong nhan `name` la), luat loi (chi cong ty / HKD,
    thieu ten, thieu ID / link, lap ID, toi da 50 dong).
  * CreatorService: sua giu `name` dong dang co (hop dong cu tro dung dong), bo `name` client bia, ghi vet
    tren creator khi danh sach doi; tao moi khong mang `name` nao.
  * kol_service: phieu chi gui kol_ref - server CHUP LAI tu creator (sua DOM khong vao hop dong); dong
    ngung dung / cua creator khac bi bo; doi sang loai HD khac thi xoa; gui ma creator co KOL ma chua chon
    thi chan.
  * kol_values: nhieu KOL -> TikTok ID / link kenh noi bang dau phay + KOL_LIST_DISPLAY / KOL_NAMES_DISPLAY;
    khong chon -> dung kenh tren creator nhu cu.
  * Khai bao: 2 DocType con, Custom Field Supplier.ec_cr_kols (fixtures + hooks), kol_channels tren form 27,
    p587 resync + ban ke sha256.
Chay: python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hop_dong_nhieu_kol_27_11.py
"""
import datetime
import hashlib
import importlib
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:                    # cong push chay `python -m unittest <module>`
    sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
APP = os.path.join(ROOT, "ecentric_workspace")

from test_creators_service import FakeRepo  # noqa: E402

from ecentric_workspace.approval_center.shared.creators import domain  # noqa: E402
from ecentric_workspace.approval_center.shared.creators.service import CreatorError, CreatorService  # noqa: E402

P = "ecentric_workspace.approval_center.features.contract_review."
KOL_TYPE = "KOL/KOC / Creator (EC)"
CTY = {"name": "SUP-001", "supplier_name": "Cty Media A", "ec_cr_type": "Công ty", "tax_id": "0312345678",
       "ec_bank_account_no": "0011", "owner": "an@ec",
       "kols": [{"name": "KOL-1", "kol_name": "Bé A", "tiktok_id": "@bea", "disabled": 0},
                {"name": "KOL-2", "kol_name": "Bé B", "tiktok_id": "beb", "disabled": 0},
                {"name": "KOL-3", "kol_name": "Bé C (thôi)", "tiktok_id": "bec", "disabled": 1}]}


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


class DanhSachKolDomain(unittest.TestCase):
    def test_lam_sach_bo_dong_trong_va_name_la(self):
        rows = [{"kol_name": " Bé A ", "tiktok_id": "@bea", "name": "KOL-1"},
                {"kol_name": "", "tiktok_id": "  "},
                {"kol_name": "Bé X", "tiktok_id": "x", "name": "KOL-CUA-NGUOI-KHAC", "disabled": "1"},
                "rac"]
        out = domain.clean_kols(rows, keep_names=["KOL-1"])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["kol_name"], "Bé A")
        self.assertEqual(out[0]["name"], "KOL-1")
        self.assertNotIn("name", out[1])
        self.assertEqual(out[1]["disabled"], 1)

    def test_luat_loi(self):
        ok = [{"kol_name": "A", "tiktok_id": "a"}, {"kol_name": "B", "shopee_url": "https://shopee.vn/b"}]
        self.assertEqual(domain.kol_errors(ok, "Công ty"), [])
        self.assertEqual(domain.kol_errors(ok, "Hộ kinh doanh"), [])
        self.assertTrue(domain.kol_errors(ok, "Cá nhân"))
        # Ca nhan chi con dong ngung dung: khong chan (doi loai sau khi tich ngung dung het).
        self.assertEqual(domain.kol_errors([dict(ok[0], disabled=1)], "Cá nhân"), [])
        self.assertTrue(any("thiếu tên" in e for e in domain.kol_errors([{"tiktok_id": "a"}], "Công ty")))
        self.assertTrue(any("thiếu TikTok ID" in e for e in domain.kol_errors([{"kol_name": "A"}], "Công ty")))
        dup = [{"kol_name": "A", "tiktok_id": "@abc"}, {"kol_name": "B", "tiktok_id": "https://www.tiktok.com/@ABC"}]
        self.assertTrue(any("lặp" in e for e in domain.kol_errors(dup, "Công ty")))
        many = [{"kol_name": "K%d" % i, "tiktok_id": "k%d" % i} for i in range(domain.KOL_MAX + 1)]
        self.assertTrue(domain.kol_errors(many, "Công ty"))

    def test_validate_payload_va_view(self):
        bad = {"supplier_name": "Cty", "ec_cr_type": "Công ty", "tax_id": "0312345678",
               "ec_cr_kols": [{"kol_name": "A"}]}
        self.assertTrue(any("KOL" in e for e in domain.validate_payload(bad)))
        view = domain.public_view(CTY, False)
        self.assertEqual([k["name"] for k in view["kols"]], ["KOL-1", "KOL-2", "KOL-3"])
        self.assertEqual(view["kols"][2]["disabled"], 1)
        self.assertNotIn("ec_cr_cccd", view["kols"][0])


class SuaCreator(unittest.TestCase):
    def _svc(self):
        return CreatorService(FakeRepo([CTY], {"ke.toan@ec": ["EC Finance"]}))

    def test_sua_giu_name_dong_cu_bo_name_bia_va_ghi_vet(self):
        s = self._svc()
        rows = [{"name": "KOL-1", "kol_name": "Bé A", "tiktok_id": "@bea"},
                {"name": "KOL-BIA", "kol_name": "Bé D", "tiktok_id": "bed"}]
        s.update("an@ec", "SUP-001", {"ec_cr_kols": json.dumps(rows)})
        name, values = s.repo.updated[-1]
        kols = values["ec_cr_kols"]
        self.assertEqual(kols[0]["name"], "KOL-1")
        self.assertNotIn("name", kols[1])
        self.assertTrue(any("danh sách KOL" in n for n in s.repo.notes))

    def test_khong_doi_thi_khong_ghi_danh_sach(self):
        s = self._svc()
        same = [{k: r.get(k) for k in ("name", "kol_name", "tiktok_id", "disabled")} for r in CTY["kols"]]
        s.update("an@ec", "SUP-001", {"ec_cr_kols": same, "ec_phone": "0909"})
        self.assertNotIn("ec_cr_kols", s.repo.updated[-1][1])

    def test_sai_thi_bao_loi(self):
        with self.assertRaises(CreatorError):
            self._svc().update("an@ec", "SUP-001", {"ec_cr_kols": [{"kol_name": "Thiếu ID"}]})
        with self.assertRaises(CreatorError):
            self._svc().update("an@ec", "SUP-001", {"ec_cr_kols": "{khong phai json"})

    def test_tao_moi_khong_mang_name(self):
        s = CreatorService(FakeRepo([], {}))
        data = {"supplier_name": "Cty Mới", "ec_cr_type": "Công ty", "tax_id": "0312345679",
                "ec_cr_kols": [{"name": "KOL-1", "kol_name": "Bé A", "tiktok_id": "bea"}]}
        s.create("an@ec", data)
        self.assertEqual(s.repo.inserted[-1]["ec_cr_kols"], [{"kol_name": "Bé A", "tiktok_id": "bea", "channel_url": "",
                                                               "shopee_id": "", "shopee_url": "", "disabled": 0}])


class PhieuChonKol(unittest.TestCase):
    def setUp(self):
        from test_contract_kol_qc_15_11 import Doc, _fresh
        self.Doc = Doc
        self.ks = _fresh("an@ec")[0]

    def _doc(self, chans, **kw):
        d = self.Doc(doctype="EC Contract Review Request", name="CR-1", contract_type=KOL_TYPE, creator="SUP-001",
                     kol_channels=chans)
        d.update(kw)
        return d

    def test_chup_lai_tu_creator_khong_tin_client(self):
        d = self._doc([{"kol_ref": "KOL-2", "kol_name": "TEN SUA TRONG DOM", "tiktok_id": "hack"},
                       {"kol_ref": "KOL-2"}, {"kol_ref": "KOL-3"}, {"kol_ref": "KOL-CUA-CTY-KHAC"},
                       {"kol_ref": "KOL-1"}])
        self.ks.snapshot_kols(d, CTY)
        got = [(r["kol_ref"], r["kol_name"], r["tiktok_id"]) for r in d["kol_channels"]]
        self.assertEqual(got, [("KOL-2", "Bé B", "beb"), ("KOL-1", "Bé A", "@bea")])

    def test_gui_ma_chua_chon_thi_chan(self):
        d = self._doc([])
        self.ks.snapshot_kols(d, CTY)
        self.assertIn("chọn ít nhất một KOL", self.ks.kol_channel_error(d, CTY))
        self.assertIsNone(self.ks.kol_channel_error(d, dict(CTY, kols=[])))
        self.ks.snapshot_kols(d, dict(CTY, kols=[]))
        d2 = self._doc([{"kol_ref": "KOL-1"}])
        self.ks.snapshot_kols(d2, CTY)
        self.assertIsNone(self.ks.kol_channel_error(d2, CTY))

    def test_noi_vao_luong_luu_va_gui(self):
        src = _read("approval_center/features/contract_review/application/kol_service.py")
        self.assertIn("snapshot_kols(doc, creator)", src)
        self.assertIn('doc.set("kol_channels", [])', src)      # loai HD khac: xoa
        self.assertIn("kol_err = kol_channel_error(doc, creator)", src)


class GiaTriHopDong(unittest.TestCase):
    def setUp(self):
        self.V = importlib.import_module(P + "domain.kol_values")

    def _vals(self, doc, creator):
        base = {"creator_type": "Công ty", "service_type": "Livestream", "platform": "TikTok"}
        base.update(doc)
        return self.V.contract_values(base, creator, "", None, [datetime.date(2026, 12, 1)])

    def test_nhieu_kol(self):
        v = self._vals({"kol_channels": [{"kol_name": "Bé A", "tiktok_id": "@bea"},
                                         {"kol_name": "Bé B", "tiktok_id": "beb",
                                          "channel_url": "https://www.tiktok.com/@beb.live"}]},
                       {"supplier_name": "Cty A", "ec_cr_tiktok_id": "congty"})
        self.assertEqual(v["TIKTOK_ID_DISPLAY"], "bea, beb")
        self.assertEqual(v["CHANNEL_URL"], "https://www.tiktok.com/@bea, https://www.tiktok.com/@beb.live")
        self.assertEqual(v["KOL_NAMES_DISPLAY"], "Bé A, Bé B")
        self.assertEqual(v["KOL_LIST_DISPLAY"].split("\n")[0], "Bé A – @bea – https://www.tiktok.com/@bea")
        self.assertIn("KOL_LIST_DISPLAY", self.V.PLACEHOLDER_HELP)

    def test_khong_chon_thi_nhu_cu(self):
        v = self._vals({"creator_type": "Cá nhân"}, {"ec_cr_tiktok_id": "https://www.tiktok.com/@abc?x=1"})
        self.assertEqual(v["TIKTOK_ID_DISPLAY"], "abc")
        self.assertEqual(v["CHANNEL_URL"], "https://www.tiktok.com/@abc")
        self.assertEqual(v["KOL_NAMES_DISPLAY"], "")

    def test_shopee(self):
        v = self._vals({"platform": "Shopee", "kol_channels": [{"kol_name": "S1", "shopee_id": "s1"},
                                                               {"kol_name": "S2", "shopee_url": "https://shopee.vn/s2x"}]},
                       {})
        self.assertEqual(v["CHANNEL_URL"], "https://shopee.vn/s1, https://shopee.vn/s2x")
        self.assertEqual(v["CHANNEL_ID_DISPLAY"], "s1")


class KhaiBao(unittest.TestCase):
    def test_doctype_va_custom_field(self):
        kol = json.loads(_read("approval_center/doctype/ec_creator_kol/ec_creator_kol.json"))
        snap = json.loads(_read("approval_center/doctype/ec_contract_review_kol/ec_contract_review_kol.json"))
        for d, name in ((kol, "EC Creator KOL"), (snap, "EC Contract Review KOL")):
            self.assertEqual(d["name"], name)
            self.assertEqual(d["istable"], 1)
            self.assertEqual(d["field_order"], [f["fieldname"] for f in d["fields"]])
        self.assertTrue(set(domain.KOL_FIELDS) <= {f["fieldname"] for f in kol["fields"]})
        self.assertTrue(set(domain.KOL_FIELDS) | {"kol_ref"} <= {f["fieldname"] for f in snap["fields"]})
        cf = [x for x in json.loads(_read("fixtures/custom_field.json")) if x.get("name") == "Supplier-ec_cr_kols"]
        self.assertEqual(len(cf), 1)
        self.assertEqual((cf[0]["fieldtype"], cf[0]["options"]), ("Table", "EC Creator KOL"))
        self.assertIn('"Supplier-ec_cr_kols"', _read("hooks.py"))
        cr = json.loads(_read("approval_center/doctype/ec_contract_review_request/ec_contract_review_request.json"))
        f = next(x for x in cr["fields"] if x["fieldname"] == "kol_channels")
        self.assertEqual((f["fieldtype"], f["options"]), ("Table", "EC Contract Review KOL"))
        self.assertIn("kol_channels", cr["field_order"])
        self.assertIn('"kol_channels"', _read("approval_center/features/contract_review/domain/definition.py"))

    def test_trang_va_patch(self):
        key = "approval_center/features/contract_review/ui/main_section.html"
        html = _read(key)
        for mark in ("kolPickHTML", "kc-kol-add", "data.ec_cr_kols=kols", 'KOL.kolsText(b)', '"kol_channels"]'):
            self.assertIn(mark, html)
        self.assertNotIn("{{", html)
        man = json.loads(_read("approval_center/patches/resync_manifest.json"))
        with open(os.path.join(APP, key), "rb") as fh:
            self.assertEqual(man[key]["sha256"], hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest())
        self.assertTrue(os.path.exists(os.path.join(APP, "approval_center", "patches",
                                                    man[key]["last_resync_patch"] + ".py")))
        lines = [ln for ln in _read("patches.txt").splitlines() if ln.strip()]
        self.assertEqual(lines.count("ecentric_workspace.approval_center.patches.p587_resync_hop_dong_nhieu_kol"), 1)
        marks = re.search(r"_MARKS = \(([^)]*)\)", _read("approval_center/patches/p587_resync_hop_dong_nhieu_kol.py"),
                          re.S).group(1)
        for m in re.findall(r'"([^"]+)"', marks):
            self.assertIn(m, html)


if __name__ == "__main__":
    unittest.main()
