# Copyright (c) 2026, eCentric and contributors
"""Kien thuc ERP cho AI (Hoan 27/11/2026): bao quat ERP nhung TUYET DOI theo quyen; cam luong /
thuong / PnL / doanh thu; khong nguon nao doc du lieu do.

    python3 ecentric_workspace/platform/ai/tests/test_knowledge.py

Nap ma nguon THAT (knowledge_sources.py, knowledge.py, guides/registry.py, cac trang huong dan
that trong guides/pages) bang exec - khong qua __pycache__. Module cua tung trang ERP la gia.
"""
import inspect
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.dirname(HERE)
APP = os.path.dirname(os.path.dirname(AI))


def _mod(full, path=None, **attrs):
    m = types.ModuleType(full)
    if path:
        m.__file__ = path
    m.__dict__.update(attrs)
    sys.modules[full] = m
    pkg, _, short = full.rpartition(".")
    if pkg in sys.modules:
        setattr(sys.modules[pkg], short, m)
    if path and path.endswith(".py"):
        with open(path, encoding="utf-8") as fh:
            exec(compile(fh.read(), path, "exec"), m.__dict__)
    return m


class World(object):
    def __init__(self, user="nv@ec.vn", roles=("Employee",)):
        self.logs, self.calls = [], []
        env = self
        fk = types.ModuleType("frappe")
        fk.session = types.SimpleNamespace(user=user)
        fk.get_roles = lambda u=None: list(roles)
        fk.log_error = lambda *a, **k: env.logs.append(k.get("title"))
        fk._ = lambda s: s
        sys.modules["frappe"] = fk
        self.frappe = fk
        for pkg in ("ecentric_workspace", "ecentric_workspace.platform", "ecentric_workspace.platform.ai"):
            sys.modules[pkg] = types.ModuleType(pkg)
        # Goi y that: guides/registry.py + thu muc guides/pages that.
        g = _mod("ecentric_workspace.guides", os.path.join(APP, "guides", "__init__.py"))
        g.__file__ = os.path.join(APP, "guides", "__init__.py")
        self.registry = _mod("ecentric_workspace.guides.registry", os.path.join(APP, "guides", "registry.py"))
        self.S = _mod("ecentric_workspace.platform.ai.knowledge_sources", os.path.join(AI, "knowledge_sources.py"))
        self.k = _mod("ecentric_workspace.platform.ai.knowledge", os.path.join(AI, "knowledge.py"))

    def fake(self, full, **attrs):
        parts = full.split(".")
        for i in range(1, len(parts)):
            p = ".".join(parts[:i])
            if p not in sys.modules:
                _mod(p)
        return _mod(full, **attrs)


class VungCam(unittest.TestCase):
    def setUp(self):
        self.k = World().k

    def test_luong_thuong_bi_chan(self):
        for msg in ("lương của chị Linh bao nhiêu", "thưởng tết năm nay mỗi người bao nhiêu",
                    "tiền thưởng của anh A", "bonus Q4", "CTC của tôi", "bảng lương phòng Media",
                    "thu nhap trung binh"):
            self.assertEqual(self.k.guard(msg), self.k.SALARY_REPLY, msg)

    def test_pnl_doanh_thu_bi_chan(self):
        for msg in ("doanh thu tháng này bao nhiêu", "lợi nhuận phòng Ecom", "cho xem P&L Q3",
                    "PnL brand Vinasoy", "lãi lỗ công ty", "biên lợi nhuận", "chi phí nhân sự toàn công ty",
                    "quỹ lương", "revenue of eCentric", "kết quả kinh doanh quý 3"):
            self.assertIsNotNone(self.k.guard(msg), msg)
        self.assertEqual(self.k.guard("doanh thu tháng này"), self.k.PNL_REPLY)

    def test_khong_bat_nham_cau_binh_thuong(self):
        for msg in ("chất lượng báo cáo tuần", "số lượng khảo sát", "luồng duyệt phiếu",
                    "phần thưởng quiz tuần này", "thường xuyên đi muộn thì sao", "lượt nói",
                    "làm sao tạo đề nghị thanh toán", "ai là trưởng phòng Data"):
            self.assertIsNone(self.k.guard(msg), msg)

    def test_eC_Mate_tao_phieu_co_chu_doanh_thu_van_di_tiep_nhung_hoi_thi_chan(self):
        k = self.k
        tao = "tạo đề nghị xuất hóa đơn doanh thu brand Vinasoy"
        self.assertIsNone(k.guard(tao, creating_ok=True))
        self.assertEqual(k.guard(tao), k.PNL_REPLY, "o chat hoi dap: van chan")
        self.assertEqual(k.guard("doanh thu tháng 10 bao nhiêu", creating_ok=True), k.PNL_REPLY)
        self.assertEqual(k.guard("tạo phiếu ghi lương của anh A", creating_ok=True), k.SALARY_REPLY,
                         "luong thi khong co ngoai le")


class KhongNguonNaoDocVungCam(unittest.TestCase):
    def test_quet_ma_nguon_tung_nguon(self):
        w = World()
        for key, (_t, fn) in w.k.SOURCES.items():
            code = inspect.getsource(fn)
            for bad in ("Salary", "salary", "Payroll", "payroll", "bank_ac", "ctc", "pnl", "PnL",
                        "revenue", "ignore_permissions", "nbv", "gross"):
                self.assertNotIn(bad, code, "%s doc %s" % (key, bad))

    def test_danh_ba_qua_get_list_co_kiem_quyen_cot_co_dinh(self):
        code = inspect.getsource(World().S.directory)
        self.assertIn("frappe.get_list", code)
        self.assertNotIn("get_all", code)
        for bad in ("cell_number", "personal_email", "date_of_birth", "current_address", "passport"):
            self.assertNotIn(bad, code)

    def test_tai_san_khong_lot_gia_tri_khi_nguoi_hoi_la_quan_ly(self):
        w = World()
        w.fake("ecentric_workspace.tai_san.controllers.api", my_assets=lambda: {"success": True, "data": {
            "assets": [{"tag": "LT-01", "asset_name": "Laptop Dell", "category": "Laptop", "status_label": "Đang dùng",
                        "condition": "Tốt", "gross": 25000000, "nbv": 12345678, "monthly": 700000,
                        "pending_ack": True}],
            "licenses": [{"license_name": "Office 365", "vendor": "Microsoft", "expiry_date": "2027-01-01"}]}})
        out = "\n".join(w.S.assets("nv@ec.vn"))
        self.assertIn("LT-01 Laptop Dell", out)
        self.assertIn("CHO BAN XAC NHAN", out)
        self.assertIn("Office 365", out)
        for bad in ("25000000", "12345678", "700000"):
            self.assertNotIn(bad, out)

    def test_ban_do_erp_an_pnl(self):
        S = World().S
        out = S.map_lines([{"group": "Doanh thu & Lợi nhuận", "label": "Doanh thu (PnL)", "route": "/pnl-dashboard"},
                           {"group": "Nhân sự", "label": "Chấm công", "route": "/ec-hr/attendance"}])
        self.assertEqual(len(out), 1)
        self.assertIn("/ec-hr/attendance: cham cong", out[0])


class HuongDanThat(unittest.TestCase):
    """Doc bai huong dan THAT trong repo -> AI tra loi duoc 'lam X the nao'."""

    def setUp(self):
        self.w = World()
        self.S, self.reg = self.w.S, self.w.registry

    def test_html_text_bo_script_style_giu_danh_sach(self):
        t = self.S.html_text("<style>.a{}</style><h2>Buoc 1</h2><script>var x=1</script>"
                             "<ul><li>Mo /approvals</li><li>Chon &quot;DNTT&quot;</li></ul><svg><path/></svg>")
        self.assertEqual(t, "Buoc 1\n- Mo /approvals\n- Chon \"DNTT\"")

    def test_chon_dung_bai_theo_cau_hoi(self):
        idx = self.reg.listed()
        got = self.S.match_guides("làm sao để đề nghị mua hàng rồi đề nghị thanh toán", idx)
        self.assertEqual(got[0], "dnmh-dntt")
        # bai thu hai lac de (kem xa bai dau) khong kem vao; bai sat chu de (vd hop-dong co DNTT)
        # duoc phep - main them bai moi thi danh sach doi.
        self.assertNotIn("nghi-viec-clearance", got)
        self.assertIn("chot-cong-thang", self.S.match_guides("chốt công tháng hạn khi nào", idx))
        self.assertEqual(self.S.match_guides("chào bạn", idx), [])
        self.assertEqual(self.S.match_guides("hôm nay ăn gì", idx), [])

    def test_moi_bai_trong_registry_doc_ra_chu(self):
        for g in self.reg.listed():
            t = self.S.guide_text(g["slug"])
            self.assertGreater(len(t), 200, g["slug"])
            self.assertNotIn("<", t[:200], g["slug"])
            self.assertLessEqual(len(t), self.S.GUIDE_TEXT_CHARS)
            self.assertNotIn("MSO Request", t, "vo menu shell khong duoc lot vao: " + g["slug"])

    def test_slug_la_khong_doc_file_ngoai(self):
        self.assertEqual(self.S.guide_text("../../hooks"), "")
        self.assertEqual(self.S.guide_text("khong-co-bai-nay"), "")


class NguonGia(unittest.TestCase):
    def test_viec_cua_toi(self):
        w = World()
        w.fake("ecentric_workspace.action_center.feed", build_feed=lambda user, limit=20: {
            "total": 2, "counts": {"overdue": 1, "act_now": 1},
            "items": [{"bucket": "overdue", "source_label": "Phê duyệt", "title": "DNTT-001",
                       "subtitle": "Chờ bạn duyệt cấp 2", "due_at": "2026-11-26 17:00:00",
                       "action_url": "/approvals/payment-request?name=DNTT-001"}]})
        out = w.S.mywork("nv@ec.vn")
        self.assertIn("QUA HAN 1", out[0])
        self.assertIn("[QUA HAN] Phê duyệt: DNTT-001 - Chờ bạn duyệt cấp 2 (han 2026-11-26 17:00)", out[1])

    def test_sla_ty_le_da_la_phan_tram(self):
        w = World()
        w.fake("ecentric_workspace.sla.controllers.api", my_board=lambda period=None: {"data": {
            "period": "2026-11", "overall": {"rate": 87.5, "ontime": 7, "late": 1, "missed": 0, "open": 2},
            "groups": [{"label": "Phê duyệt", "rate": 0.5, "scored": 2, "late": 1, "counts_toward_sla": True}]}})
        out = w.S.sla("nv@ec.vn")
        self.assertIn("87.5% dung han", out[0])
        self.assertIn("Phê duyệt: 0.5%", out[1])

    def test_context_luon_co_ban_do_huong_dan_phieu_va_bo_nguon_hong(self):
        w = World()
        k = w.k
        k.SOURCES[k.MYWORK] = ("Viec", lambda u: ["[LAM NGAY] task A"])
        k.SOURCES[k.CATALOG] = ("Phieu", lambda u: ["Đề nghị thanh toán (PAYMENT_REQUEST) - /approvals/x"])
        k.SOURCES[k.MAP] = ("Ban do", lambda u: ["Nhân sự › Chấm công - /ec-hr/attendance"])

        def hong(u):
            raise RuntimeError("chua cai")
        k.SOURCES[k.ATTENDANCE] = ("Cham cong", hong)
        text, picked = k.context("nv@ec.vn", "làm sao đề nghị mua hàng, chấm công của tôi")
        self.assertIn(k.ATTENDANCE, picked)
        for need in ("task A", "PAYMENT_REQUEST", "/ec-hr/attendance", "Bai huong dan su dung",
                     "Noi dung bai huong dan sat cau hoi", "[Bai dnmh-dntt - /huong-dan/dnmh-dntt]"):
            self.assertIn(need, text)
        self.assertNotIn("=== Cham cong ===", text)
        self.assertIn("ai_knowledge attendance", w.logs)

    def test_chon_nguon_moi(self):
        k = World().k
        self.assertIn(k.ATTENDANCE, k.pick_sources("tháng này mình đi muộn mấy lần"))
        self.assertIn(k.DIRECTORY, k.pick_sources("ai là trưởng phòng Data"))
        self.assertIn(k.ASSETS, k.pick_sources("laptop của tôi bảo hành tới khi nào"))
        self.assertIn(k.TODAY, k.pick_sources("tuần này có sinh nhật ai"))
        self.assertIn(k.SLA, k.pick_sources("điểm SLA của mình"))
        self.assertTrue(k.about_work("làm sao đổi mật khẩu ERP"))
        self.assertFalse(k.about_work("tìm giúp mình trang web xem phim vui"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
