# Copyright (c) 2026, eCentric and contributors
"""Ban giao chat Ky so -> chat Hop dong 23/11/2026 (B1-B6):

B1 o "Ban PDF de ky" + tu dat o ky (kol_sign_pdf), B2 hook doi chieu tep ky (esign_hooks.verify_document +
domain.sign_pdf_check), B3 moc [[KY_BEN_A]] / [[KY_BEN_B]] trong mau Word (domain.sign_anchors + p480),
B4 khoa goi khi gui (esign_gate trong service.submit / resubmit), B5 bao nguoi lap khi bi tra lai,
B6 hook doi tac ky (esign_hooks.external_handlers). Frappe gia nhu cac test KOL khac.
"""
import importlib
import io
import os
import re
import sys
import types
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import CR, STATE, Doc, Throw, _fresh  # noqa: E402

APP = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO = os.path.abspath(os.path.join(APP, "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
P = "ecentric_workspace.approval_center.features.contract_review.application."
D = "ecentric_workspace.approval_center.features.contract_review.domain."


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


# ----------------------------------------------------------------------------- docx gia lap 2 bo cuc that
_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _p(text=""):
    return '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % text


def _grid(*cols):
    g = "".join('<w:gridCol w:w="%d"/>' % c for c in cols)
    # 18 mau Ke toan deu co tblGridChange (luoi cu ghi lai) - doc nham thanh 4 cot la sai be rong.
    return '<w:tblGrid>%s<w:tblGridChange w:id="1"><w:tblGrid>%s</w:tblGrid></w:tblGridChange></w:tblGrid>' % (g, g)


def _cell(*paras):
    return "<w:tc><w:tcPr><w:vAlign w:val=\"top\"/></w:tcPr>%s</w:tc>" % "".join(paras)


def _bbnt_xml():
    """BBNT: bang 2 cot, hang tieu de + dong trong, hang ten (o khong co tcW)."""
    body = "".join(_p("Nội dung %d" % i) for i in range(5))
    body += ("<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/></w:tblPr>%s"
             "<w:tr>%s%s</w:tr><w:tr>%s%s</w:tr></w:tbl>"
             % (_grid(4590, 4435), _cell(_p("ĐẠI DIỆN BÊN A"), _p(), _p(), _p()), _cell(_p("ĐẠI DIỆN BÊN B"), _p()),
                _cell(_p("NGUYỄN VĂN LÃM")), _cell(_p("&lt;&lt;SIGNATORY_B_UPPER&gt;&gt;"))))
    body += _p("Đính kèm Biên bản nghiệm thu hợp đồng Số &lt;&lt;CONTRACT_NO&gt;&gt;")
    return body


def _hddv_xml():
    """HĐDV: bang tieu de 'Thay mặt và đại diện cho' 2 cot, doan trong ngoai bang, MOT doan hai ten."""
    body = "".join(_p("Điều %d" % i) for i in range(5))
    body += ("<w:tbl><w:tblPr><w:jc w:val=\"center\"/></w:tblPr>%s<w:tr>%s%s</w:tr></w:tbl>"
             % (_grid(4678, 4820), _cell(_p("Thay mặt và đại diện cho"), _p("CÔNG TY TNHH ECENTRIC")),
                _cell(_p("Thay mặt và đại diện cho"), _p("BÊN B"))))
    body += _p() * 4
    body += _p("     NGUYỄN VĂN LÃM          &lt;&lt;SIGNATORY_B_UPPER&gt;&gt;")
    body += _p("&lt;&lt;PERSON_ID_NO&gt;&gt;")
    return body


def _docx(body):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s>'
                   '<w:body>%s<w:sectPr/></w:body></w:document>' % (_W, body))
    return buf.getvalue()


def _xml(data):
    return zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")


def _anchors():
    sys.modules.pop(D + "sign_anchors", None)
    return importlib.import_module(D + "sign_anchors")


# ----------------------------------------------------------------------------- B3
class MocKyTrongMau(unittest.TestCase):
    def test_bbnt_moc_dau_o_hang_ten_lui_giua_cot(self):
        sa = _anchors()
        new, rep = sa.add_markers(_docx(_bbnt_xml()))
        self.assertEqual(rep, {"status": "added", "how": "row"})
        xml = _xml(new)
        # moc A ngay truoc ten CEO, moc B ngay truoc <<SIGNATORY_B>> - cung hang ten
        self.assertLess(xml.index("[[KY_BEN_A]]"), xml.index("NGUYỄN VĂN LÃM"))
        self.assertLess(xml.index("NGUYỄN VĂN LÃM"), xml.index("[[KY_BEN_B]]"))
        self.assertLess(xml.index("[[KY_BEN_B]]"), xml.index("&lt;&lt;SIGNATORY_B_UPPER"))
        # o khong ghi tcW -> lay luoi bang (2 cot, KHONG doc tblGridChange thanh 4 cot)
        self.assertIn('w:left="%d"' % ((4590 - 3600) // 2), xml)
        self.assertIn('w:left="%d"' % ((4435 - 3600) // 2), xml)
        # chu trang 1pt, KHONG an (Word bo chu an khi xuat PDF)
        self.assertEqual(xml.count('<w:color w:val="FFFFFF"/><w:sz w:val="2"/>'), 2)
        self.assertNotIn("<w:vanish", xml)
        self.assertTrue(sa.has_markers(new))

    def test_hddv_chen_bang_2_cot_truoc_doan_ten(self):
        sa = _anchors()
        new, rep = sa.add_markers(_docx(_hddv_xml()))
        self.assertEqual(rep["how"], "table")
        xml = _xml(new)
        i_tbl = xml.rindex("<w:tbl>", 0, xml.index("[[KY_BEN_A]]"))
        self.assertLess(xml.index("[[KY_BEN_B]]"), xml.index("NGUYỄN VĂN LÃM"))
        seg = xml[i_tbl:xml.index("</w:tbl>", i_tbl)]
        self.assertIn('<w:gridCol w:w="4678"/><w:gridCol w:w="4820"/>', seg)   # luoi bang tieu de
        self.assertIn('<w:jc w:val="center"/>', seg)                            # can bang nhu bang tieu de
        self.assertIn('w:val="nil"', seg)                                        # khong vien

    def test_chay_lai_khong_chen_hai_lan(self):
        sa = _anchors()
        once, _r = sa.add_markers(_docx(_bbnt_xml()))
        twice, rep = sa.add_markers(once)
        self.assertEqual(rep["status"], "already")
        self.assertEqual(once, twice)

    def test_bo_cuc_la_khong_sua(self):
        sa = _anchors()
        data = _docx(_p("Không có chỗ ký"))
        out, rep = sa.add_markers(data)
        self.assertEqual(rep["status"], "not_found")
        self.assertEqual(out, data)

    def test_dien_mau_giu_nguyen_moc(self):
        """Hop dong sinh tu mau (docx_fill) phai con moc - moc khong phai <<placeholder>>."""
        sa = _anchors()
        df = importlib.import_module(D + "docx_fill")
        marked, _r = sa.add_markers(_docx(_bbnt_xml()))
        filled, missing = df.fill_docx(marked, {"SIGNATORY_B_UPPER": "TRẦN THỊ B", "CONTRACT_NO": "01/HDDV"})
        self.assertTrue(sa.has_markers(filled))
        self.assertEqual(missing, [])
        self.assertIn("TRẦN THỊ B", _xml(filled))

    def test_patch_co_sao_luu_va_khong_nem(self):
        src = _read("patches/p480_moc_ky_mau_hop_dong.py")
        self.assertIn("Bản trước:", src)              # ghi duong dan tep cu (sao luu) vao Ghi chu
        self.assertIn('"is_private": 1', src)
        self.assertNotIn("delete_doc", src)           # khong xoa tep cu
        self.assertIn("frappe.log_error(frappe.get_traceback()", src)


# ----------------------------------------------------------------------------- B2
class DoiChieuTepKy(unittest.TestCase):
    def _check(self):
        return importlib.import_module(D + "sign_pdf_check")

    def test_khop_ca_khi_pdf_tach_chu(self):
        c = self._check()
        text = "HỢP ĐỒNG SỐ 15112026/HDDV/ ECENTRIC-NTP.FCV\nThực nhận 9,000,000 VNĐ"
        self.assertEqual(c.findings(text, {"15112026", "9000000"}, "15112026/HDDV/ECENTRIC-NTP.FCV", "9000000"), [])

    def test_sai_so_hd_hoac_so_tien(self):
        c = self._check()
        out = c.findings("HĐ 01/HDDV tổng 9,500,000", {"01", "9500000"}, "02/HDDV", "9000000")
        self.assertEqual(len(out), 2)
        self.assertIn("02/HDDV", out[0])
        self.assertIn("9,000,000", out[1])

    def test_mau_creator_chi_so_tien(self):
        c = self._check()
        self.assertEqual(c.findings("Hợp đồng của creator 9.000.000", {"9000000"}, "02/HDDV", "9000000",
                                    check_contract_no=False), [])

    def test_khong_co_chu(self):
        self.assertTrue(self._check().findings("   ", set(), "1", "1"))

    def test_so_in_tren_hop_dong(self):
        _fresh()
        kol = importlib.import_module(D + "kol")
        self.assertEqual(kol.printed_digits(8_999_999.5), "9000000")    # lam tron nua len nhu khi in
        self.assertIsNone(kol.printed_digits(0))
        self.assertIsNone(kol.printed_digits(None))


def _hooks():
    sys.modules.pop(P + "esign_hooks", None)
    return importlib.import_module(P + "esign_hooks")


def _kol_doc(**kw):
    d = Doc(doctype=CR, name="CR-1", contract_type="KOL/KOC / Creator (EC)", requested_by="req@ec", owner="req@ec",
            contract_no="23112026/HDDV/ECENTRIC-AB.X", payable_amount=9_000_000, creator="SUP-1",
            request_type="Template from EC / Mẫu theo khung EC", esign_flow="kol_wf09",
            partner_signer_name="Nguyễn Văn C", partner_signer_email="c@gmail.com", partner_signer_phone="0900",
            approval_request=None, signing_status="Chưa ký", acceptances=[])
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    return d


class HookDoiChieu(unittest.TestCase):
    def setUp(self):
        _fresh("req@ec")
        # kol_ai keo nhieu thu luc nap: chi can number_tokens
        STATE["values"][("User", "c@gmail.com")] = None

    def test_khop(self):
        _kol_doc()
        h = _hooks()
        r = h.verify_document(CR, "CR-1", "HD.pdf", ["Số: 23112026/HDDV/ECENTRIC-AB.X", "Thực nhận 9,000,000 đ"])
        self.assertEqual(r["status"], "match")

    def test_lech_so_tien(self):
        _kol_doc()
        r = _hooks().verify_document(CR, "CR-1", "HD.pdf", ["Số: 23112026/HDDV/ECENTRIC-AB.X 8,000,000"])
        self.assertEqual(r["status"], "mismatch")
        self.assertIn("9,000,000", r["reason"])

    def test_khong_chu(self):
        _kol_doc()
        self.assertEqual(_hooks().verify_document(CR, "CR-1", "x.pdf", ["", "  "])["status"], "no_text")

    def test_hop_dong_thuong_khong_doi_chieu(self):
        _kol_doc(contract_type="Purchase / Mua vào (EC)")
        self.assertEqual(_hooks().verify_document(CR, "CR-1", "x.pdf", ["bất kỳ"])["status"], "not_applicable")


class HookDoiTac(unittest.TestCase):
    def setUp(self):
        _fresh("req@ec")

    def _creator(self, **kw):
        row = {"ec_cr_type": "Cá nhân", "ec_cr_email": "C@gmail.com", "ec_cr_cccd": "001200000001",
               "ec_cr_cccd_issue_place": "Cục CS QLHC", "ec_cr_cccd_issue_date": "2021-04-01", "ec_cr_dob": "1999-02-03"}
        row.update(kw)
        STATE["values"][("Supplier", "SUP-1")] = lambda field, as_dict: row

    def test_ca_nhan_ky_chinh_minh_kem_dinh_danh(self):
        _kol_doc()
        self._creator()
        rows = _hooks().external_handlers("CR-1")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["full_name"], r["email"], r["phone"]), ("Nguyễn Văn C", "c@gmail.com", "0900"))
        self.assertEqual((r["identity_date"], r["dob"]), ("01/04/2021", "03/02/1999"))
        self.assertNotIn("sign_type", r)              # Ky so dat mac dinh (eKYC)

    def test_nguoi_ky_khac_khong_gan_cccd_creator(self):
        _kol_doc(partner_signer_email="dai.dien@cty.vn")
        self._creator(ec_cr_type="Công ty")
        r = _hooks().external_handlers("CR-1")[0]
        self.assertNotIn("identity", r)
        self.assertNotIn("dob", r)

    def test_thieu_email_bao_tieng_viet(self):
        _kol_doc(partner_signer_email="")
        self._creator()
        with self.assertRaises(Throw) as cm:
            _hooks().external_handlers("CR-1")
        self.assertIn("email", str(cm.exception))

    def test_quy_trinh_khong_doi_tac(self):
        _kol_doc(esign_flow="khong_ky_cong")
        with self.assertRaises(Throw):
            _hooks().external_handlers("CR-1")


# ----------------------------------------------------------------------------- B1
class OBanPdfDeKy(unittest.TestCase):
    def _mod(self, enabled=True):
        _fresh("req@ec")
        gate = types.ModuleType(P + "esign_gate")
        gate.enabled = lambda name: enabled
        sys.modules[P + "esign_gate"] = gate
        sys.modules.pop(P + "kol_sign_pdf", None)
        return importlib.import_module(P + "kol_sign_pdf")

    def test_ket_qua_tu_dat_o_ky_ra_cau_de_hieu(self):
        m = self._mod()
        self.assertIn("2 ô ký", m.summarize({"ok": True, "placed": [{}, {}]})["message"])
        self.assertIn("Word", m.summarize({"ok": False, "reason": "verify_no_text"})["message"])
        r = m.summarize({"ok": False, "reason": "verify_mismatch", "message": "Không thấy số tiền 9,000,000 đ"})
        self.assertFalse(r["ok"])
        self.assertIn("9,000,000", r["message"])
        self.assertIn("kéo ô ký bằng tay", m.summarize({"ok": False, "reason": "no_markers"})["message"])

    def test_chi_nguoi_lap_va_truoc_khi_gui(self):
        m = self._mod()
        _kol_doc(requested_by="khac@ec", owner="khac@ec")
        with self.assertRaises(Throw):
            m.attach("CR-1", "/private/files/HD.pdf", "req@ec")
        _kol_doc(approval_request="AR-1")
        STATE["values"][("EC Approval Request", "AR-1")] = "Pending"
        with self.assertRaises(Throw):
            m.attach("CR-1", "/private/files/HD.pdf", "req@ec")
        _kol_doc(contract_no=None)
        with self.assertRaises(Throw):
            m.attach("CR-1", "/private/files/HD.pdf", "req@ec")

    def test_khong_nhan_tep_docx_hay_tep_hop_dong(self):
        m = self._mod()
        _kol_doc(contract_file="/private/files/HDDV_1.docx")
        with self.assertRaises(Throw):
            m.attach("CR-1", "/private/files/HD.docx", "req@ec")

    def test_chua_bat_ky_so_thi_khong_goi_nen_tang(self):
        m = self._mod(enabled=False)
        r = m.place(_kol_doc(sign_pdf="/private/files/HD.pdf"))
        self.assertFalse(r["esign"])
        self.assertTrue(r["ok"])

    def test_attach_khong_goi_auto_place_cung_request(self):
        """auto_place rollback truoc khi khoa hang phieu -> goi trong cung request la xoa tep vua gan."""
        src = _read("features/contract_review/application/kol_sign_pdf.py")
        body = src[src.index("def attach("):src.index("def _drop_old(")]
        self.assertNotIn("place(", body.replace("auto_place sign", ""))
        page = _read("features/contract_review/ui/main_section.html")
        self.assertIn('call("kol_attach_sign_pdf"', page)
        self.assertIn('call("kol_auto_place_sign"', page)


# ----------------------------------------------------------------------------- B4
class KhoaGoiKhiGui(unittest.TestCase):
    def test_submit_va_resubmit_goi_gate_dung_thu_tu(self):
        src = _read("features/contract_review/application/service.py")
        sub = src[src.index("def submit(name):"):src.index("def _soi_guong_sharepoint")]
        self.assertLess(sub.index("esign_gate.before_submit(doc)"), sub.index("engine.submit("))
        self.assertLess(sub.index("engine.submit("), sub.index("esign_gate.after_submit(doc)"))
        res = src[src.index("def resubmit("):src.index("def _guard_resubmit_needs_ceo")]
        self.assertLess(res.index("esign_gate.before_submit(doc)"), res.index("engine.resubmit("))
        self.assertLess(res.index("engine.resubmit("), res.index("esign_gate.after_submit(doc)"))

    def _gate(self, profile=None, requester=False, sign_pdf=None, stale=False):
        _fresh("req@ec")
        calls = []
        g = types.ModuleType("ecentric_workspace.platform.esign.guard")
        g.get_enabled_profile = lambda *a: profile
        g.requester_signature_required = lambda *a: requester
        rq = types.ModuleType("ecentric_workspace.platform.esign.requester")
        rq.assert_ready_to_submit = lambda *a: calls.append("assert")
        rq.lock_on_submit = lambda *a: calls.append("lock") or {"locked": True}
        es = types.ModuleType("ecentric_workspace.platform.esign")
        es.guard, es.requester = g, rq
        sys.modules.update({"ecentric_workspace.platform.esign": es, "ecentric_workspace.platform.esign.guard": g,
                            "ecentric_workspace.platform.esign.requester": rq})
        sp = types.ModuleType(P + "kol_sign_pdf")
        sp.is_stale = lambda doc: stale
        sys.modules[P + "kol_sign_pdf"] = sp
        sys.modules.pop(P + "esign_gate", None)
        return importlib.import_module(P + "esign_gate"), calls, _kol_doc(sign_pdf=sign_pdf)

    def tearDown(self):
        for k in ("ecentric_workspace.platform.esign", "ecentric_workspace.platform.esign.guard",
                  "ecentric_workspace.platform.esign.requester"):
            sys.modules.pop(k, None)

    def test_chua_co_ho_so_thi_form_chay_nhu_cu(self):
        g, calls, doc = self._gate(profile=None)
        self.assertFalse(g.before_submit(doc))
        self.assertIsNone(g.after_submit(doc))
        self.assertEqual(calls, [])

    def test_co_ho_so_bat_buoc_ban_pdf_va_khoa(self):
        g, calls, doc = self._gate(profile="HD-KOL-WF09")
        with self.assertRaises(Throw):
            g.before_submit(doc)                       # chua co Ban PDF de ky
        doc.sign_pdf = "/private/files/HD.pdf"
        self.assertTrue(g.before_submit(doc))
        g.after_submit(doc)
        self.assertEqual(calls, ["assert", "lock"])

    def test_pdf_cu_hon_hop_dong_tao_lai(self):
        g, _calls, doc = self._gate(profile="HD-KOL-WF09", sign_pdf="/private/files/HD.pdf", stale=True)
        with self.assertRaises(Throw):
            g.before_submit(doc)

    def test_ho_so_nguoi_lap_ky_khong_dung_luong_nay(self):
        g, calls, doc = self._gate(profile="X", requester=True, sign_pdf="/private/files/HD.pdf")
        self.assertFalse(g.before_submit(doc))
        self.assertIsNone(g.after_submit(doc))
        self.assertEqual(calls, [])


# ----------------------------------------------------------------------------- B5 + khai bao
class KhaiBaoVaBaoNguoiLap(unittest.TestCase):
    def test_hooks_khai_hai_hook_moi(self):
        with open(os.path.join(REPO, "ecentric_workspace", "hooks.py"), encoding="utf-8") as fh:
            hooks = fh.read()
        self.assertRegex(hooks, r'ec_esign_document_verifiers = \{\s*"EC Contract Review Request":\s*'
                                r'"[a-z_.]+esign_hooks\.verify_document"')
        self.assertRegex(hooks, r'ec_esign_external_handlers = \{\s*"EC Contract Review Request":\s*'
                                r'"[a-z_.]+esign_hooks\.external_handlers"')

    def test_tra_lai_bao_nguoi_lap(self):
        _fresh("req@ec")
        sent = []
        tr = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
        tr.notify = lambda users, subject, dt_, name: sent.append((tuple(users), subject))
        sys.modules[tr.__name__] = tr
        try:
            _kol_doc(signing_status="Chưa ký")
            r = _hooks().on_signing_outcome("CR-1", "contract", "returned", detail="Sai ngày ký")
        finally:
            sys.modules.pop(tr.__name__, None)
        self.assertTrue(r["changed"])
        self.assertEqual(sent[0][0], ("req@ec",))
        self.assertIn("không ký tiếp được", sent[0][1])
        self.assertIn("Sai ngày ký", sent[0][1])
        src = _read("features/contract_review/application/esign_hooks.py")
        self.assertEqual(len(re.findall(r"\n\s+_tell_requester\(doc,", src)), 2)   # hop dong + BBNT

    def test_nguoi_lap_tai_ban_du_luc_nhap_chi_khi_co_ky_so(self):
        from test_contract_kol_po_17_11 import _access
        biz = {"name": "CR-1", "doctype": CR, "contract_type": "KOL/KOC / Creator (EC)", "creator": "SUP-1",
               "owner": "req@ec", "requested_by": None, "approval_request": None}
        for on, expect in ((False, False), (True, True)):
            a = _access("req@ec")
            STATE["values"][("Supplier", "SUP-1")] = "creator.owner@ec"
            gate = types.ModuleType(P + "esign_gate")
            gate.enabled = lambda name, on=on: on
            sys.modules[P + "esign_gate"] = gate
            try:
                self.assertEqual(a.can_download_full(dict(biz), "req@ec"), expect)
                self.assertFalse(a.can_download_full(dict(biz), "nguoi.khac@ec"))
            finally:
                sys.modules.pop(P + "esign_gate", None)

    def test_ban_pdf_de_ky_la_tep_pii(self):
        src = _read("features/contract_review/application/kol_access.py")
        self.assertIn('business.get("sign_pdf")}', src)            # _signed_urls: an voi nguoi khong duoc tai
        self.assertIn('business["sign_pdf"] = None', src)          # redact_business
        self.assertIn("make_access_log", src)                      # tai luc nhap: vet con sau khi xoa nhap

    def test_truong_moi_va_patch(self):
        import json
        dt = json.loads(_read("doctype/ec_contract_review_request/ec_contract_review_request.json"))
        f = next(x for x in dt["fields"] if x["fieldname"] == "sign_pdf")
        self.assertEqual((f["fieldtype"], f.get("permlevel"), f.get("no_copy"), f.get("read_only")), ("Attach", 1, 1, 1))
        self.assertIn("sign_pdf", dt["field_order"])
        with open(os.path.join(REPO, "ecentric_workspace", "patches.txt"), encoding="utf-8") as fh:
            patches = fh.read()
        for p in ("p480_moc_ky_mau_hop_dong", "p481_resync_hop_dong_ky_so"):
            self.assertIn("ecentric_workspace.approval_center.patches." + p, patches)
        man = _read("patches/resync_manifest.json")
        blk = man[man.index('"approval_center/features/contract_review/ui/main_section.html"'):]
        # Trang form 27 con duoc PR sau resync (vd p499 dau trang form) -> chi doi: patch resync cuoi da khai.
        last = re.search(r'"last_resync_patch": "([^"]+)"', blk[:300]).group(1)
        self.assertIn("ecentric_workspace.approval_center.patches." + last, patches)


if __name__ == "__main__":
    unittest.main()
