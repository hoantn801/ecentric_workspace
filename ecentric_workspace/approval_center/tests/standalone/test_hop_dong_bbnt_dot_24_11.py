# Copyright (c) 2026, eCentric and contributors
"""Cau C (PO chot 24/11/2026, claude/thiet-ke-bbnt-tung-dot.md): moi dot nghiem thu (BBNT) cua hop dong
KOL/KOC la MOT phieu `EC KOL Acceptance` voi chuoi duyet rieng KOL_ACCEPTANCE (KTTH -> KTT -> CEO).
  * kho kol_rounds: ban xem, dot bi tu choi / huy khong tinh vao ke hoach;
  * "Gui duyet": moi / gui lai sau "Can bo sung" / gui lai sau tu choi - chan khi dang duyet / da duyet;
  * tai ban ky chi khi dot da duyet xong; chi xoa dot nhap cuoi CHUA gui duyet (PO cau 4);
  * nguoi duyet dot tai duoc BBNT cua dot ho duyet (PO cau 3) - qua download_file (ghi vet);
  * callback Approval Center: tao / sua chung bi chan, gui chung di qua the KOL, che URL PII;
  * setup KOL_ACCEPTANCE-V1, p520 chep dong con (giu dong con - khong xoa du lieu), giao dien.
Chay: python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hop_dong_bbnt_dot_24_11.py
"""
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import CR, STATE, Doc, Row, Throw, _fresh  # noqa: E402

APP = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.dirname(os.path.dirname(APP))
P = "ecentric_workspace.approval_center.features.contract_review.application."
F = "ecentric_workspace.approval_center.features.kol_acceptance."
SENT, DRAFT, DONE = "Đã gửi ký", "Nháp", "Hoàn tất"


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


def _real_rounds():
    """kol_rounds THAT (khong gia lap) tren frappe gia cua _fresh."""
    sys.modules.pop(P + "kol_rounds", None)
    return importlib.import_module(P + "kol_rounds")


def _contract(**kw):
    d = Doc(doctype=CR, name="CR-1", contract_type="KOL/KOC / Creator (EC)", creator="SUP-1", contract_no="X/1",
            requested_by="req@ec", owner="req@ec", approval_request="AR-1", payable_amount=10_000_000,
            advance_amount=0, acceptances=[])
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    return d


class KhoDot(unittest.TestCase):
    def test_co_ghi_khop_controller(self):
        _fresh()
        kr = _real_rounds()
        ctl = _read("doctype/ec_kol_acceptance/ec_kol_acceptance.py")
        self.assertIn('FLAG = "%s"' % kr.FLAG, ctl)
        self.assertIn("frappe.flags.in_patch", ctl)

    def test_ban_xem_va_dot_bi_tu_choi_khong_tinh(self):
        _fresh()
        kr = _real_rounds()
        data = [{"name": "B1", "contract": "CR-1", "round_no": 1, "amount": 3_000_000, "status": DONE,
                 "approval_request": None},
                {"name": "B2", "contract": "CR-1", "round_no": 2, "amount": 4_000_000, "status": SENT,
                 "approval_request": "AR-2"},
                {"name": "B3", "contract": "CR-1", "round_no": 3, "amount": 2_000_000, "status": SENT,
                 "approval_request": "AR-3"}]
        STATE["get_all"]["EC KOL Acceptance"] = lambda f, kw: [dict(x) for x in data if x["contract"] == f["contract"]]
        STATE["get_all"]["EC Approval Request"] = lambda f, kw: [{"name": "AR-2", "approval_status": "Rejected"},
                                                                {"name": "AR-3", "approval_status": "Pending"}]
        rows = kr.rows(_contract())
        self.assertEqual([(r.idx, r.round_no, r.approval_status) for r in rows],
                         [(1, 1, ""), (2, 2, "Rejected"), (3, 3, "Pending")])
        self.assertEqual(kr.planned_amount(_contract()), 5_000_000)            # B2 bi tu choi: khong tinh
        self.assertEqual(kr.planned_amount(_contract(), exclude="B3"), 3_000_000)
        cv = kr.contract_view(_contract())
        self.assertEqual([r["name"] for r in cv["acceptances"]], ["B1", "B3"])
        cv = kr.contract_view(_contract(), keep="B2")                          # dot dang gui lai
        self.assertEqual([r["name"] for r in cv["acceptances"]], ["B1", "B2", "B3"])
        self.assertEqual(kr.find(_contract(), "B2").amount, 4_000_000)
        self.assertEqual(kr.rows(Doc(name=None)), [])
        v = kr.row_view(Row(name="B9", round_no=4, idx=0))
        self.assertEqual((v.idx, v.as_dict()["round_no"]), (4, 4))

    def test_phieu_moi_khong_doc_kho(self):
        _fresh()
        kr = _real_rounds()

        class New(Doc):
            def is_new(self):
                return True
        STATE["get_all"]["EC KOL Acceptance"] = lambda f, kw: self.fail("khong duoc doc")
        self.assertEqual(kr.rows(New(name="tmp")), [])


def _acc(user="req@ec", approved=True, signed=True):
    _s, _v, acc, files = _fresh(user)
    STATE["roles"][user] = ["EC Finance"] if user.startswith("fin") else []
    acc.approval_status = lambda d: acc.APPROVED if approved else "Pending"
    acc.is_signed = lambda d: signed
    acc.can_manage = lambda d, u: True
    acc.creator_row = lambda n: {"ec_cr_type": "Cá nhân"}
    access = importlib.import_module(P + "kol_access")
    access.require_open = lambda d: None
    access.payee_changed = lambda d: False
    files.acceptance_content = lambda d, r, c, tpl=None: (b"x", [])
    files.attach = lambda d, fn, c: "/private/files/BBNT_same.docx"
    return acc


class GuiDuyet(unittest.TestCase):
    def _setup(self, **row):
        acc = _acc()
        r = Row(dict({"name": "B1", "idx": 1, "round_no": 1, "status": DRAFT, "amount": 3_000_000,
                      "bbnt_file": "/private/files/BBNT_same.docx", "approval_request": None,
                      "approval_status": ""}, **row))
        d = _contract(acceptances=[r])
        eng = types.SimpleNamespace(calls=[])
        eng.submit = lambda *a, **k: eng.calls.append(("submit", a)) or "AR-NEW"
        eng.resubmit = lambda req, actor=None, restart=False: eng.calls.append(("resubmit", req, restart)) or {}
        eng.add_watchers = lambda req, users, actor=None, source=None: eng.calls.append(("watch", req, users, source))
        acc._engine = lambda: eng
        STATE["get_all"]["EC Approval Request Approver"] = lambda f, kw: ["ktth@ec", "ktt@ec", "ceo@ec", "ktt@ec"]
        return acc, d, r, eng

    def test_gui_moi_tao_yeu_cau_va_cho_nguoi_duyet_xem_hop_dong(self):
        acc, d, r, eng = self._setup()
        res = acc.send_acceptance("CR-1", "req@ec", "B1")
        self.assertEqual((res["approval_request"], r.status, r.approval_request, r.requested_by),
                         ("AR-NEW", SENT, "AR-NEW", "req@ec"))
        self.assertEqual(eng.calls[0], ("submit", ("EC KOL Acceptance", "B1", "KOL_ACCEPTANCE", "req@ec")))
        self.assertEqual(eng.calls[1], ("watch", "AR-1", ["ceo@ec", "ktt@ec", "ktth@ec"], "BBNT"))
        self.assertFalse(res["regenerated"])

    def test_dang_duyet_hoac_da_duyet_khong_gui_lai(self):
        for ap, word in (("Pending", "chờ duyệt"), ("Approved", "đã duyệt xong")):
            acc, d, r, eng = self._setup(status=SENT, approval_request="AR-2", approval_status=ap)
            with self.assertRaises(Throw) as cm:
                acc.send_acceptance("CR-1", "req@ec", "B1")
            self.assertIn(word, str(cm.exception))
            self.assertEqual(eng.calls, [])

    def test_can_bo_sung_gui_tiep_yeu_cau_cu(self):
        acc, d, r, eng = self._setup(status=SENT, approval_request="AR-2", approval_status="Information Required")
        acc.send_acceptance("CR-1", "req@ec", "B1")
        self.assertEqual(eng.calls[0], ("resubmit", "AR-2", False))
        # BBNT doi sau khi bo sung -> duyet lai tu dau.
        acc2, d2, r2, eng2 = self._setup(status=SENT, approval_request="AR-2", approval_status="Information Required",
                                         bbnt_file="/private/files/BBNT_old.docx")
        res = acc2.send_acceptance("CR-1", "req@ec", "B1")
        self.assertEqual((eng2.calls[0], res["regenerated"]), (("resubmit", "AR-2", True), True))

    def test_bi_tu_choi_gui_lai_la_yeu_cau_moi_va_kiem_lai_tran(self):
        acc, d, r, eng = self._setup(status=SENT, approval_request="AR-2", approval_status="Rejected")
        acc.send_acceptance("CR-1", "req@ec", "B1")
        self.assertEqual((eng.calls[0][0], r.approval_request), ("submit", "AR-NEW"))
        # Trong luc bi tu choi da tao dot khac lap day hop dong -> khong gui lai duoc (vuot tran).
        acc, d, r, eng = self._setup(status=SENT, approval_request="AR-2", approval_status="Rejected")
        d["acceptances"].append(Row(name="B2", idx=2, round_no=2, status=DRAFT, amount=9_000_000,
                                    approval_request=None, approval_status=""))
        with self.assertRaises(Throw) as cm:
            acc.send_acceptance("CR-1", "req@ec", "B1")
        self.assertIn("Vượt", str(cm.exception))

    def test_bam_hai_lan_cung_luc_khong_tao_hai_yeu_cau(self):
        acc, d, r, eng = self._setup()
        kr = importlib.import_module(P + "kol_rounds")
        kr.lock = lambda name: "AR-KHAC"                  # lan bam truoc vua tao yeu cau
        with self.assertRaises(Throw) as cm:
            acc.send_acceptance("CR-1", "req@ec", "B1")
        self.assertIn("tải lại", str(cm.exception))
        self.assertEqual(eng.calls, [])
        src = _read("features/contract_review/application/kol_rounds.py")
        self.assertIn('for_update=True', src)

    def test_dot_cu_da_gui_ky_ngoai_erp_khong_gui_duyet(self):
        acc, d, r, eng = self._setup(status=SENT)
        with self.assertRaises(Throw):
            acc.send_acceptance("CR-1", "req@ec", "B1")

    def test_hop_dong_chua_duyet_xong_khong_gui(self):
        acc, d, r, eng = self._setup()
        acc.is_signed = lambda doc: False
        with self.assertRaises(Throw):
            acc.send_acceptance("CR-1", "req@ec", "B1")
        self.assertEqual(eng.calls, [])

    def test_nut_gui_duyet(self):
        acc = _acc()
        cs = acc._can_send
        self.assertTrue(cs({"status": DRAFT}))
        self.assertFalse(cs({"status": SENT}))
        self.assertTrue(cs({"status": SENT, "approval_request": "A", "approval_status": "Information Required"}))
        self.assertTrue(cs({"status": SENT, "approval_request": "A", "approval_status": "Cancelled"}))
        self.assertFalse(cs({"status": SENT, "approval_request": "A", "approval_status": "Pending"}))
        self.assertFalse(cs({"status": DONE, "approval_request": "A", "approval_status": "Rejected"}))


class TaiBanKyVaXoa(unittest.TestCase):
    def test_chua_duyet_xong_chua_tai_ban_ky(self):
        acc = _acc()
        r = Row(name="B1", idx=1, round_no=1, status=SENT, amount=1, approval_request="AR-2", approval_status="Pending")
        _contract(acceptances=[r])
        with self.assertRaises(Throw) as cm:
            acc.complete_acceptance("CR-1", "req@ec", "B1", "/private/files/k.pdf")
        self.assertIn("chưa duyệt xong", str(cm.exception))

    def test_da_duyet_tai_ban_ky_duoc(self):
        acc = _acc()
        r = Row(name="B1", idx=1, round_no=1, status=SENT, amount=1, approval_request="AR-2", approval_status="Approved")
        _contract(acceptances=[r])
        files = importlib.import_module(P + "kol_files")
        files.claim_upload = lambda d, url, u: url
        seen = []
        acc.finish_round = lambda d, row, f, w, by: seen.append((row.name, f, by)) or []
        acc.complete_acceptance("CR-1", "req@ec", "B1", "/private/files/k.pdf")
        self.assertEqual(seen, [("B1", "/private/files/k.pdf", "req@ec")])

    def test_chi_xoa_dot_nhap_cuoi_chua_gui_duyet(self):
        acc = _acc()
        r1 = Row(name="B1", idx=1, round_no=1, status=DRAFT, amount=1, approval_request=None)
        r2 = Row(name="B2", idx=2, round_no=2, status=DRAFT, amount=1, approval_request="AR-9",
                 approval_status="Rejected")
        _contract(acceptances=[r1, r2])
        with self.assertRaises(Throw) as cm:
            acc.delete_acceptance("CR-1", "req@ec", "B2")         # da tung gui duyet: giu vet
        self.assertIn("chưa gửi duyệt", str(cm.exception))
        with self.assertRaises(Throw) as cm:
            acc.delete_acceptance("CR-1", "req@ec", "B1")         # khong phai dot cuoi
        self.assertIn("cuối cùng", str(cm.exception))
        d = _contract(acceptances=[Row(name="B1", idx=1, round_no=1, status=DRAFT, amount=1, approval_request=None)])
        importlib.import_module(P + "kol_files")._drop_generated = lambda *a, **k: None
        self.assertEqual(acc.delete_acceptance("CR-1", "req@ec", "B1"), {"deleted": "B1"})
        self.assertEqual(d["acceptances"], [])


class XoaTepSauCommit(unittest.TestCase):
    """Prod 24/11: xoa tep cu trong after_commit cua request -> DELETE bi rollback, byte da mat (5 ban ghi
    File mo coi o 00119 / 00130 / 00133). Nay xoa trong job nen xep sau commit (job tu commit)."""

    def test_xep_job_sau_commit_khong_xoa_ngay(self):
        _fresh("req@ec")
        files = importlib.import_module(P + "kol_files")
        fk = sys.modules["frappe"]
        jobs, deleted = [], []
        fk.enqueue = lambda method, **kw: jobs.append((method, kw))
        fk.delete_doc = lambda dt_, n, **kw: deleted.append(n)
        STATE["get_all"]["File"] = lambda f, kw: ["F-1", "F-2"]
        d = _contract(approval_request=None)
        files._drop_generated(d, "/private/files/HDDV_x.docx")
        self.assertEqual(deleted, [])
        self.assertEqual(jobs[0][0].rsplit(".", 1)[-1], "drop_files")
        self.assertEqual((jobs[0][1]["names"], jobs[0][1]["enqueue_after_commit"]), (["F-1", "F-2"], True))
        STATE["exists"].add(("File", "F-1"))
        files.drop_files(["F-1", "F-2"])                  # F-2 da mat: bo qua
        self.assertEqual(deleted, ["F-1"])
        jobs.clear()
        files._drop_generated(_contract(approval_request="AR-1"), "/private/files/HDDV_x.docx")
        self.assertEqual(jobs, [])                        # phieu da gui: giu tep lam vet
        src = _read("features/contract_review/application/kol_files.py")
        i = src.index("def _drop_generated")
        self.assertNotIn("after_commit", src[i:src.index("def drop_files")].split('"""', 2)[2].split("# Xoa trong JOB")[0])


class NguoiDuyetDot(unittest.TestCase):
    def test_nguoi_duyet_dot_tai_duoc_ban_cua_dot_do(self):
        _fresh("ceo@ec")
        access = importlib.import_module(P + "kol_access")
        d = _contract(acceptances=[Row(name="B1", idx=1, round_no=1, bbnt_file="/private/files/BBNT_a.docx",
                                       signed_file=None, approval_request="AR-B1"),
                                   Row(name="B2", idx=2, round_no=2, bbnt_file="/private/files/BBNT_b.docx",
                                       approval_request="AR-B2")])
        STATE["exists"].add(("EC Approval Request Approver", (("approval_request", "AR-B1"), ("approver", "ceo@ec"))))
        self.assertEqual(access.round_approver_files(d, "ceo@ec"), {"/private/files/BBNT_a.docx"})
        self.assertEqual(access.round_approver_files(d, "Guest"), set())
        src = _read("features/contract_review/application/kol_access.py")
        i = src.index("def download_file")
        body = src[i:src.index("\ndef ", i + 5)]
        self.assertIn("round_approver_files(doc, user)", body)
        self.assertIn("doc.add_comment", body)                    # van ghi vet moi lan tai

    def test_bang_dot_khong_che_url_cua_dot_ho_duyet(self):
        src = _read("features/contract_review/application/kol_service.py")
        i = src.index("def _rows_for")
        body = src[i:src.index("\ndef ", i + 5)]
        self.assertIn("mine = kol_access.round_approver_files(business, user)", body)
        self.assertIn('r.get("bbnt_file") not in mine', body)


class KySoDotCoChuoiDuyet(unittest.TestCase):
    def test_cong_bao_ky_du_khi_dot_chua_duyet_thi_tu_choi(self):
        _fresh()
        hooks = importlib.import_module(P + "esign_hooks")
        r = Row(name="B1", idx=1, round_no=1, status=SENT, approval_request="AR-B1", approval_status="Pending")
        d = _contract(acceptances=[r], signed_file="/hd.pdf")
        STATE["values"][("EC Approval Request", "AR-B1")] = "Pending"
        with self.assertRaises(ValueError):
            hooks._round(d, "B1", "signed", "/b.pdf", None)
        res = hooks._round(d, "B1", "returned", None, "sai")
        self.assertEqual((res["changed"], r.status), (True, SENT))     # giu trang thai, chi ghi vet + bao


def _feature_service():
    _fresh("req@ec")
    sys.modules.pop(F + "application.service", None)
    return importlib.import_module(F + "application.service")


class CallbackApprovalCenter(unittest.TestCase):
    def test_tao_sua_chung_bi_chan(self):
        svc = _feature_service()
        with self.assertRaises(Throw) as cm:
            svc.prepare_draft(Doc(contract="CR-1"))
        self.assertIn("thẻ KOL", str(cm.exception))

    def test_gui_chung_di_qua_the_kol(self):
        svc = _feature_service()
        STATE["values"][("EC KOL Acceptance", "B1")] = lambda field, as_dict: "CR-1"
        acc = importlib.import_module(P + "kol_acceptance")
        calls = []
        acc.send_acceptance = lambda c, u, n: calls.append((c, u, n)) or {"approval_request": "AR-7", "regenerated": True}
        self.assertEqual(svc.submit("B1"), "AR-7")
        self.assertEqual(svc.resubmit("B1", "req@ec"), {"restarted": True})
        self.assertEqual(calls, [("CR-1", "req@ec", "B1")] * 2)

    def test_che_url_pii_trong_chi_tiet(self):
        svc = _feature_service()
        biz = {"bbnt_file": "/private/files/BBNT_a.docx", "signed_file": None, "sign_pdf": "/private/files/x.pdf"}
        svc.redact_business(biz)
        self.assertEqual((biz["bbnt_file"], biz["sign_pdf"], biz["has_bbnt_file"], biz["has_signed_file"]),
                         (None, None, True, False))

    def test_dinh_kem_pii_an_voi_nguoi_ngoai(self):
        svc = _feature_service()
        svc._may_download = lambda b, u: False
        att = [{"file_url": "/private/files/BBNT_a.docx", "file_name": "BBNT_a.docx", "owner": "Administrator"},
               {"file_url": "/private/files/ghichu.pdf", "file_name": "ghichu.pdf", "owner": "req@ec"},
               {"file_url": "/private/files/ky.pdf", "file_name": "ky.pdf", "owner": "req@ec"}]
        out = svc.redact_attachments(att, {"sign_pdf": "/private/files/ky.pdf"})
        self.assertEqual([a["file_name"] for a in out], ["ghichu.pdf"])
        svc._may_download = lambda b, u: True
        self.assertEqual(len(svc.redact_attachments(att, {})), 3)

    def test_dang_ky_dinh_nghia_va_handler(self):
        defn = _read("features/kol_acceptance/domain/definition.py")
        for cb in ("prepare_draft", "round_block", "redact_attachments", "redact_business"):
            self.assertIn('"%s"' % cb, defn)
        self.assertIn("editable_fields=()", defn)
        reg = _read("shared/registry.py")
        self.assertIn("KOL_ACCEPTANCE_DEFINITION,", reg)
        tr = _read("shared/workflow/transitions.py")
        self.assertIn('"EC KOL Acceptance": "ecentric_workspace.approval_center.features.kol_acceptance.'
                      'application.service.on_final_approval"', tr)
        self.assertTrue(os.path.exists(os.path.join(APP, "features/kol_acceptance/controllers/api.py")))


class CauHinhVaDiTru(unittest.TestCase):
    def test_quy_trinh_3_cap_bat_buoc(self):
        src = _read("features/kol_acceptance/infrastructure/setup.py")
        self.assertEqual(src.count('"mandatory": 1'), 2)          # L1 + ham chep (L2, L3)
        self.assertIn("LEVELS = 3", src)
        self.assertNotIn("@ecentric.vn", src)                     # khong ghi cung nguoi trong code nghiep vu
        p = _read("patches/p520_bbnt_tung_dot.py")
        self.assertIn('KTTH = "lien.vu@ecentric.vn"', p)          # PO 24/11 cau 2 - tham so setup
        self.assertNotIn("delete", p.lower().replace("khong xoa", "").replace("không xoá", ""))

    def test_p520_chep_dong_con_chay_lai_an_toan(self):
        _fresh()
        sys.modules.pop("ecentric_workspace.approval_center.patches.p520_bbnt_tung_dot", None)
        p = importlib.import_module("ecentric_workspace.approval_center.patches.p520_bbnt_tung_dot")
        child = [{"name": "row1", "parent": "CR-1", "idx": 1, "description": "Live", "acceptance_date": "2026-11-20",
                  "amount": 5, "status": DONE, "bbnt_file": "/b.docx", "signed_file": "/s.pdf",
                  "completed_at": None, "completed_by": "ai@ec", "due_date": None, "check_note": None,
                  "verified_by": "x"}]
        STATE["get_all"]["EC Contract Acceptance"] = lambda f, kw: [Row(x) for x in child]
        STATE["values"][(CR, "CR-1")] = lambda field, as_dict: Row(name="CR-1", contract_no="X/1", creator="S",
                                                                  creator_name="A", brand="B", company="C",
                                                                  department="D", requested_by="req@ec", owner="o")
        made = []

        class NewDoc(Row):
            flags = types.SimpleNamespace()

            def insert(self, **kw):
                made.append(dict(self))
                STATE["exists"].add(("EC KOL Acceptance", (("legacy_row", self["legacy_row"]),)))
        sys.modules["frappe"].get_doc = lambda d, name=None: NewDoc(d)
        self.assertEqual(p.migrate_rows(), (1, 0))
        self.assertEqual((made[0]["round_no"], made[0]["status"], made[0]["legacy_row"], made[0]["completed_by"],
                          made[0]["contract"]), (1, DONE, "row1", None, "CR-1"))
        self.assertEqual(p.migrate_rows(), (0, 1))                 # chay lai: bo qua

    def test_bang_con_an_va_patch_dung_thu_tu(self):
        cr = json.loads(_read("doctype/ec_contract_review_request/ec_contract_review_request.json"))
        f = next(x for x in cr["fields"] if x["fieldname"] == "acceptances")
        self.assertEqual((f.get("hidden"), f.get("read_only")), (1, 1))
        ka = json.loads(_read("doctype/ec_kol_acceptance/ec_kol_acceptance.json"))
        idx = {x["fieldname"]: x for x in ka["fields"]}
        self.assertEqual(idx["contract"].get("search_index"), 1)
        self.assertEqual(idx["signed_file"].get("permlevel"), 1)
        with open(os.path.join(ROOT, "ecentric_workspace", "patches.txt"), encoding="utf-8") as fh:
            lines = [x.strip() for x in fh if x.strip()]
        i514 = lines.index("ecentric_workspace.approval_center.patches.p514_hop_dong_quy_trinh_v2")
        i516 = lines.index("ecentric_workspace.approval_center.patches.p520_bbnt_tung_dot")
        i517 = lines.index("ecentric_workspace.approval_center.patches.p521_resync_hop_dong_bbnt_duyet")
        self.assertLess(i514, i516)
        self.assertLess(i516, i517)
        seed = json.loads(_read("seed/approval_types_seed.json"))
        self.assertTrue(any(r["approval_code"] == "KOL_ACCEPTANCE" for r in seed))

    def test_manifest_khop_nguon_trang(self):
        man = json.loads(_read("patches/resync_manifest.json"))
        key = "approval_center/features/contract_review/ui/main_section.html"
        with open(os.path.join(APP, "features/contract_review/ui/main_section.html"), "rb") as fh:
            # Ban clone Windows (core.autocrlf) doi xuong dong thanh CRLF; ma bam tinh tren ban LF cua repo.
            self.assertEqual(man[key]["sha256"], hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest())
        # p521 hoac mot patch resync SAU no trong patches.txt (vd p540 bang tinh bien lai 24/11).
        order = [ln.rsplit(".", 1)[-1] for ln in _read("../patches.txt").splitlines() if ln.strip()]
        last = man[key]["last_resync_patch"]
        self.assertIn(last, order)
        self.assertGreaterEqual(order.index(last), order.index("p521_resync_hop_dong_bbnt_duyet"))
        html = _read("features/contract_review/ui/main_section.html")
        marks = re.search(r"_MARKS = \(([^)]*)\)", _read("patches/p521_resync_hop_dong_bbnt_duyet.py")).group(1)
        for m in re.findall(r'"([^"]+)"', marks):
            self.assertIn(m, html)
        self.assertNotIn("{{", html)


def _extract(src, start):
    """Than ham JS tu `start` (vd 'acceptanceTable:function(x){') toi dau } dong cung cap."""
    i = src.index(start) + len(start)
    depth, j = 1, i
    while depth:
        ch = src[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        j += 1
    return src[src.index(start):j]


class GiaoDien(unittest.TestCase):
    def test_bang_dot_theo_trang_thai_duyet(self):
        html = _read("features/contract_review/ui/main_section.html")
        parts = [_extract(html, k) for k in ("accBadge:function(st){", "accState:function(r){",
                                             "accSignable:function(r){", "acceptanceTable:function(x){")]
        ap = re.search(r"ACC_AP:\{[^\n]*\},", html).group(0)
        js = r"""
var window={location:{search:"?id=CR-1&bbnt=B3"}};
function esc(s){ return String(s==null?"":s); }
var KOL={ money:function(v){return String(v);}, day:function(v){return String(v);}, dlLink:function(u,l){return "<a>"+l+"</a>";},
  noteHTML:function(){return "";}, calcHTML:function(){return "";},
  %s
};
var rows=[{name:"B1",idx:1,status:"Hoàn tất",approval_request:"AR-1",approval_status:"Approved"},
          {name:"B2",idx:2,status:"Đã gửi ký",approval_request:"AR-2",approval_status:"Pending"},
          {name:"B3",idx:3,status:"Đã gửi ký",approval_request:"AR-3",approval_status:"Rejected",can_send:true},
          {name:"B4",idx:4,status:"Đã gửi ký",approval_request:"AR-4",approval_status:"Approved"},
          {name:"B5",idx:5,status:"Nháp",approval_request:"",approval_status:"",can_send:true}];
var h=KOL.acceptanceTable({acceptances:rows,can_manage:true,closed:null});
function rowOf(n){ var i=h.indexOf('data-label="Đợt">'+n+'<'); var j=h.indexOf("</tr>",i); return h.slice(i,j); }
console.log(JSON.stringify({
  b2:rowOf(2), b3:rowOf(3), b4:rowOf(4), b5:rowOf(5), hl:/<tr class="kol-hl"><td data-label="Đợt">3</.test(h),
  guide:/Gửi duyệt/.test(h)}));
""" % ",\n  ".join([ap.rstrip(",")] + parts)
        if not shutil.which("node"):
            # May khong co node (vd ban clone Windows chua cai): chi kiem tinh - cong JS cua push script bao rieng.
            self.assertIn("KOL.accSignable(r)", parts[3])
            self.assertIn("r.can_send", parts[3])
            return
        # Chu Viet: ghi JS ra tep UTF-8 (khong qua argv) va doc stdout bang utf-8 - Windows mac dinh cp1252
        # lam vo bai test o cong push 24/11.
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(js)
        self.addCleanup(os.unlink, fh.name)
        out = subprocess.run(["node", fh.name], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        r = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertIn("Chờ duyệt", r["b2"])
        self.assertNotIn('data-kol="doneacc"', r["b2"])                 # dang duyet: chua tai ban ky
        self.assertNotIn('data-kol="sendacc"', r["b2"])
        self.assertIn("Bị từ chối", r["b3"])
        self.assertIn("Gửi duyệt lại", r["b3"])
        self.assertNotIn('data-kol="delacc"', r["b3"])
        self.assertIn('data-kol="doneacc"', r["b4"])                    # da duyet: tai ban ky
        self.assertIn("Đã duyệt · chờ ký", r["b4"])
        self.assertIn(">Gửi duyệt<", r["b5"])
        self.assertIn('data-kol="delacc"', r["b5"])                     # nhap cuoi chua gui: xoa duoc
        self.assertTrue(r["hl"] and r["guide"])

    def test_mo_tu_link_phieu_dot(self):
        html = _read("features/contract_review/ui/main_section.html")
        i = html.index("function renderDetail(b){")
        body = html[i:html.index("call(\"get_detail\"", i)]
        self.assertIn("/^EC-BBNT-/", body)
        self.assertIn('call("kol_round_contract",{name:rid})', body)
        self.assertIn("go({id:r.contract,bbnt:r.round", body)
        api = _read("features/contract_review/controllers/api.py")
        self.assertRegex(api, r"kol_round_contract[,)]")


class MoTrangTuPhieuDot(unittest.TestCase):
    def test_chi_nguoi_xem_duoc_phieu_dot(self):
        acc = _acc("x@ec")
        STATE["values"][("EC KOL Acceptance", "B1")] = lambda field, as_dict: Row(
            name="B1", contract="CR-1", requested_by="req@ec", approval_request="AR-B1")
        perm = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
        perm.can_view_request = lambda req, user=None, **k: user == "ceo@ec"
        sys.modules[perm.__name__] = perm
        import ecentric_workspace.approval_center.shared.workflow as wf
        old = getattr(wf, "permissions", None)
        wf.permissions = perm
        self.addCleanup(lambda: (sys.modules.pop(perm.__name__, None), setattr(wf, "permissions", old)))
        self.assertEqual(acc.round_contract("B1", "ceo@ec"), {"contract": "CR-1", "round": "B1"})
        with self.assertRaises(Throw):
            acc.round_contract("B1", "x@ec")


if __name__ == "__main__":
    unittest.main()
