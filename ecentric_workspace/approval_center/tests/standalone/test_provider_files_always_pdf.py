# Copyright (c) 2026, eCentric and contributors
"""Moi tep gui nha cung cap phai la PDF THAT (05/09, EC-PAYR-2026-00042).

Chi Hien dinh kem `p-mob.png` lam phu luc. ERP gui no cho eContract voi FileType "pdf" va
byte PNG. AddDocument 2xx, Trinh ky 2xx, roi eContract im lang: khong chu ky, task ket
"Cho gui di", 20 phut sau Manual Review `provider_accepted_but_silent`. Phieu 00053 hom
truoc (chi mot PDF, cung nguoi/token/nguoi nhan) ky trong 3 giay.

  1. render.to_pdf: PDF giu nguyen; PNG/JPEG -> PDF that (Pillow THAT); khac -> tu choi.
     delivery_for_name: PDF as_is / anh rendered_pdf / con lai erp_only.
  2. package.preflight_for_lock (code THAT): phu luc Excel KHONG bi chan (giu tren ERP);
     to trinh khong PDF van bi chan (signable_not_pdf).
  3. scts.create_document (AST): chot byte %PDF truoc khi dung payload.
  4. tasks._provider_file (AST): ve anh, doi ten .pdf, ghi su kien; phu luc khong ve duoc
     -> None + SupportingFileKeptInErp; to trinh khong ve duoc -> ProviderError.
  5. DocType Event co hai gia tri moi; document_setup tra provider_delivery.
"""
import ast
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(rel):
    with io.open(os.path.join(_ESIGN, rel), encoding="utf-8") as fh:
        return fh.read()


def _load(rel, name):
    m = types.ModuleType(name)
    exec(compile(_read(rel), rel, "exec"), m.__dict__)
    return m


def _png(mode="RGBA", size=(40, 30)):
    from PIL import Image
    im = Image.new(mode, size, (200, 30, 30, 0) if mode == "RGBA" else (200, 30, 30))
    buf = io.BytesIO(); im.save(buf, format="PNG"); return buf.getvalue()


def _jpeg():
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (20, 20), (0, 0, 255)).save(buf, format="JPEG")
    return buf.getvalue()


class TestRender(unittest.TestCase):
    def setUp(self):
        self.r = _load("render.py", "_render_under_test")

    def test_kind_theo_byte_khong_theo_ten(self):
        self.assertEqual(self.r.kind_of(b"%PDF-1.4 ..."), "pdf")
        self.assertEqual(self.r.kind_of(_png()), "png")
        self.assertEqual(self.r.kind_of(_jpeg()), "jpeg")
        self.assertIsNone(self.r.kind_of(b"PK\x03\x04docx"))
        self.assertIsNone(self.r.kind_of(b""))

    def test_pdf_giu_nguyen(self):
        out, conv = self.r.to_pdf(b"%PDF-1.7\n%%EOF", "a.pdf")
        self.assertEqual(out, b"%PDF-1.7\n%%EOF"); self.assertFalse(conv)

    def test_png_co_alpha_thanh_pdf_that(self):
        out, conv = self.r.to_pdf(_png("RGBA"), "p-mob.png")
        self.assertTrue(conv); self.assertTrue(out.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", out[-64:])

    def test_vung_trong_suot_thanh_trang_khong_thanh_den(self):
        from PIL import Image
        im = Image.new("RGBA", (4, 4), (0, 0, 0, 0))          # hoan toan trong suot
        im.putpixel((0, 0), (10, 20, 30, 255))
        rgb = self.r.flatten_to_rgb(im)
        self.assertEqual(rgb.mode, "RGB")
        self.assertEqual(rgb.getpixel((3, 3)), (255, 255, 255))
        self.assertEqual(rgb.getpixel((0, 0)), (10, 20, 30))
        self.assertEqual(self.r.flatten_to_rgb(Image.new("L", (2, 2), 7)).mode, "RGB")

    def test_jpeg_thanh_pdf(self):
        out, conv = self.r.to_pdf(_jpeg(), "anh.jpg")
        self.assertTrue(conv); self.assertTrue(out.startswith(b"%PDF"))

    def test_docx_bi_tu_choi(self):
        with self.assertRaises(self.r.UnrenderableFile):
            self.r.to_pdf(b"PK\x03\x04 not an image", "bang.docx")

    def test_doi_ten_va_mime(self):
        self.assertEqual(self.r.pdf_file_name("p-mob.png"), "p-mob.pdf")
        self.assertEqual(self.r.pdf_file_name("hoa don.JPEG"), "hoa don.pdf")
        self.assertTrue(self.r.is_renderable_mime("image/png"))
        self.assertTrue(self.r.is_renderable_mime("application/pdf"))
        self.assertFalse(self.r.is_renderable_mime("application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        self.assertFalse(self.r.is_renderable_mime(None))

    def test_delivery_theo_ten(self):
        self.assertEqual(self.r.delivery_for_name("a.PDF"), "as_is")
        self.assertEqual(self.r.delivery_for_name("p-mob.png"), "rendered_pdf")
        self.assertEqual(self.r.delivery_for_name("hd.JPG"), "rendered_pdf")
        self.assertEqual(self.r.delivery_for_name("thong_ke_item_GBS.xlsx"), "erp_only")
        self.assertEqual(self.r.delivery_for_name(None), "erp_only")


def _package_module(files, levels=()):
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})

    def throw(msg, exc=None):
        raise (exc or Exception)(msg)
    fk.throw = throw

    class _DB(object):
        def get_value(self, dt, name, fields=None, as_dict=False, **k):
            return types.SimpleNamespace(profile="P", status="Draft")

        def count(self, *a, **k):
            return 0
    fk.db = _DB()
    fk.get_all = lambda dt, **k: list(levels) if dt == "EC Digital Signature Profile Level" else []
    mods = {"frappe": fk, "frappe.utils": types.ModuleType("frappe.utils"),
            "ecentric_workspace.platform.esign.events": types.ModuleType("e"),
            "ecentric_workspace.platform.esign.hashing": types.ModuleType("h"),
            "ecentric_workspace.platform.esign.permissions": types.ModuleType("p")}
    mods["frappe.utils"].now_datetime = lambda: None
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_package_under_test")
        exec(compile(_read("package.py"), "package.py", "exec"), m.__dict__)
        m.package_files = lambda pkg: [types.SimpleNamespace(**f) for f in files]
        m.package_placements = lambda pkg: []
        errs = m.preflight_for_lock("PKG-1")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return errs


def _row(name, mime, is_pdf, sig):
    return {"name": "DSF-" + name, "file_name": name, "mime_type": mime, "is_pdf": is_pdf,
            "requires_signature": sig, "sha256": "x", "size_bytes": 10}


class TestPreflight(unittest.TestCase):
    def test_phu_luc_anh_va_pdf_duoc_qua(self):
        errs = _package_module([_row("a.pdf", "application/pdf", 1, 1),
                                _row("p-mob.png", "image/png", 0, 0),
                                _row("hd.jpg", "image/jpeg", 0, 0)])
        self.assertEqual(errs, [])

    def test_phu_luc_excel_khong_bi_chan_vi_giu_tren_erp(self):
        errs = _package_module([_row("a.pdf", "application/pdf", 1, 1),
                                _row("bang.xlsx", "application/vnd.ms-excel", 0, 0)])
        self.assertEqual(errs, [])

    def test_tep_ky_khong_pdf_van_bao_ma_cu(self):
        errs = _package_module([_row("a.png", "image/png", 0, 1)])
        self.assertIn("signable_not_pdf:a.png", errs)
        self.assertNotIn("supporting_not_renderable:a.png", errs)


def _package_for_count(total, kept_metas):
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})
    fk.throw = lambda msg, exc=None: (_ for _ in ()).throw((exc or Exception)(msg))
    fk.db = types.SimpleNamespace(count=lambda dt, flt=None: total)
    fk.get_all = lambda dt, filters=None, pluck=None, **k: list(kept_metas) \
        if (dt == "EC Digital Signature Event" and (filters or {}).get("event_type") == "SupportingFileKeptInErp") else []
    fk.parse_json = json.loads
    mods = {"frappe": fk, "frappe.utils": types.ModuleType("frappe.utils"),
            "ecentric_workspace.platform.esign.events": types.ModuleType("e"),
            "ecentric_workspace.platform.esign.hashing": types.ModuleType("h"),
            "ecentric_workspace.platform.esign.permissions": types.ModuleType("p")}
    mods["frappe.utils"].now_datetime = lambda: None
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_package_under_test2")
        exec(compile(_read("package.py"), "package.py", "exec"), m.__dict__)
        return m.provider_file_count("PKG-1")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class TestProviderFileCount(unittest.TestCase):
    """00043 (06/09 00:34): goi 3 dong, Excel giu tren ERP, SCTS co 2 tep -> verify tra
    file_count_mismatch mai; chu ky that cua Hien khong bao gio duoc xac nhan."""

    def test_tru_phu_luc_giu_tren_erp(self):
        self.assertEqual(_package_for_count(3, ['{"file": "thong_ke_item_GBS.xlsx", "order": 0}']), 2)

    def test_tao_lai_nhieu_lan_khong_tru_doi(self):
        metas = ['{"file": "a.xlsx"}', '{"file": "a.xlsx"}', '{"file": "b.docx"}', 'not json']
        self.assertEqual(_package_for_count(5, metas), 3)

    def test_goi_cu_khong_su_kien_thi_dem_du(self):
        self.assertEqual(_package_for_count(3, []), 3)

    def test_service_dung_ham_nay_o_ca_hai_cho(self):
        src = ast.unparse(ast.parse(_read("service.py")))
        self.assertIn("file_count = pkgsvc.provider_file_count(dsr.package)", src)
        self.assertIn("expected_files = pkgsvc.provider_file_count(package_name)", src)
        self.assertNotIn("frappe.db.count('EC Digital Signature File', {'package': dsr.package})", src)


class TestAdapterAndTasks(unittest.TestCase):
    def test_adapter_chot_byte_pdf_truoc_khi_dung_payload(self):
        src = _read(os.path.join("providers", "scts.py"))
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)
              and n.name == "create_document"][0]
        body = ast.unparse(fn)
        i_guard = body.index("scts_non_pdf_payload")
        i_b64 = body.index("b64 = self._b64(f.get('content'))")
        self.assertLess(i_guard, i_b64, "chot phai dung TRUOC khi ma hoa payload")
        self.assertIn("[:4] == b'%PDF'", body)
        self.assertIn("retryable=False", body[i_guard - 200:i_guard + 300])

    def test_tasks_ve_anh_doi_ten_ghi_su_kien_va_tu_choi_ro(self):
        src = _read("tasks.py")
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_provider_file"][0]
        body = ast.unparse(fn)
        self.assertIn("render.to_pdf(content, name)", body)
        self.assertIn("render.pdf_file_name(name)", body)
        self.assertIn("events.emit('SupportingFileRendered'", body)
        self.assertIn("except render.UnrenderableFile", body)
        self.assertIn("if f.requires_signature:", body)
        self.assertIn("ProviderError('unrenderable_package_file'", body)
        self.assertIn("retryable=False", body)
        self.assertIn("events.emit('SupportingFileKeptInErp'", body)
        self.assertIn("return None", body)
        # ctx.files phai di qua helper nay - khong con dict tay noi khac
        whole = ast.unparse(tree)
        self.assertIn("'files': [x for x in (_provider_file(pkg, i, f) for (i, f) in enumerate(files)) if x]", whole)
        self.assertEqual(whole.count("'can_be_signed': f.requires_signature"), 1)

    def test_doctype_event_va_read_model(self):
        p = os.path.join(_APP, "ecentric_workspace", "approval_center", "doctype",
                         "ec_digital_signature_event", "ec_digital_signature_event.json")
        with io.open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        opts = [x for x in d["fields"] if x["fieldname"] == "event_type"][0]["options"].split("\n")
        self.assertIn("SupportingFileRendered", opts)
        self.assertIn("SupportingFileKeptInErp", opts)
        self.assertIn("'provider_delivery': render.delivery_for_name(rep.get('file_name'), req_sig)",
                      ast.unparse(ast.parse(_read("document_setup.py"))))


if __name__ == "__main__":
    unittest.main()
