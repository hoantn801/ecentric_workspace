# Copyright (c) 2026, eCentric and contributors
"""ec-bw-proxy-v1 (Hoan 06/10): lead nop thay phieu ty trong brand cho nguoi chua nop.

Chay khong can bench. Nap FILE NGUON that cua routing.py / team_service.py, chi thay
frappe, engine va repository bang ban gia (rule 13) - khong copy logic sang day."""
import importlib.util
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.abspath(os.path.join(HERE, "..", "..", "features", "brand_weight"))
P = "ecentric_workspace.approval_center"


class Throw(Exception):
    pass


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


def _throw(msg, exc=None):
    raise Throw(msg)


class _NS(dict):
    __getattr__ = dict.get


_mod("frappe", throw=_throw, _=lambda s: s, utils=_mod("frappe.utils", now_datetime=lambda: "now"))
for n in ("ecentric_workspace", P, P + ".shared", P + ".shared.workflow", P + ".features",
          P + ".features.brand_weight", P + ".features.brand_weight.application",
          P + ".features.brand_weight.infrastructure", P + ".features.brand_weight.domain"):
    _mod(n)

ENGINE = _mod(P + ".shared.workflow.transitions", calls=[])
ENGINE.resolve_department_manager_user = lambda d: None
ENGINE.approve = lambda req, actor=None, comment=None: ENGINE.calls.append(("approve", req, actor))
READER = _mod(P + ".features.brand_weight.infrastructure.employee_reader", lead_user=lambda e: None)
REPO = _mod(P + ".features.brand_weight.infrastructure.brand_weight_repository")
_mod(P + ".features.brand_weight.infrastructure", brand_weight_repository=REPO, employee_reader=READER)
SERVICE = _mod(P + ".features.brand_weight.application.service", submitted=[])
_mod(P + ".features.brand_weight.application.period_service", check_period=lambda p: None)
_mod(P + ".features.brand_weight.application.weights", diff_text=lambda a, b: "", parse_weights=lambda r: dict(r),
     prev_period=lambda p: "2026-08", same=lambda a, b: a == b)


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(FEAT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load("domain/status.py", P + ".features.brand_weight.domain.status")
routing = _load("application/routing.py", P + ".features.brand_weight.application.routing")
_mod(P + ".features.brand_weight.application", service=SERVICE)
ts = _load("application/team_service.py", "_bw_team_service")

A, LEAD, HEAD, EMP = "a@x", "lead@x", "head@x", "emp@x"


class Rule(unittest.TestCase):
    def r(self, actor=LEAD, emp=EMP, lead=LEAD, head=HEAD, st="none", sf=False):
        return routing.proxy_rule(actor, emp, lead, head, st, sf)

    def test_lead_nop_thay_nguoi_chua_nop_chuyen_truong_phong(self):
        self.assertEqual(self.r(), (True, "", False))
        self.assertEqual(self.r(st="draft")[0], True)

    def test_lead_cung_la_truong_phong_thi_chot_luon(self):
        self.assertEqual(self.r(head=LEAD), (True, "", True))

    def test_nhan_vien_la_truong_phong_thi_lead_nop_la_chot(self):
        self.assertEqual(self.r(head=EMP)[2], True)

    def test_khong_co_lead_thi_truong_phong_nop_va_chot(self):
        self.assertEqual(self.r(actor=HEAD, lead=None), (True, "", True))
        self.assertFalse(self.r(actor=A, lead=None)[0])

    def test_truong_phong_khong_vuot_lead(self):
        ok, why, _ = self.r(actor=HEAD)
        self.assertFalse(ok)
        self.assertIn("lead trực tiếp", why)

    def test_phieu_da_nop_tra_lai_chot_khong_nop_thay(self):
        for st in ("wait_lead", "wait_head", "final", "returned", "rejected"):
            self.assertFalse(self.r(st=st)[0], st)

    def test_management_tu_chot_khong_nop_thay(self):
        self.assertFalse(self.r(sf=True)[0])

    def test_chua_co_tai_khoan_hoac_chinh_minh(self):
        self.assertIn("tài khoản", self.r(emp=None)[1])
        self.assertFalse(self.r(actor=EMP, lead=EMP)[0])


class FakeRepo:
    def __init__(self, existing=None, pending_after=True, final=False):
        self.existing, self.pending_after, self.final = existing, pending_after, final
        self.writes, self.notes, self.created = [], [], []

    def active_brand_ids(self):
        return {"B1", "B2"}

    def employee_row(self, e):
        return _NS(name=e, user_id=EMP, department="Ops - EC", employee_name="Huy")

    def find_doc(self, e, p):
        return self.existing

    def payload(self, name):
        if name == "BW-1" and self.writes:
            return {"approval_status": "Approved" if self.final else "Pending", "current_level": 2}
        return {"approval_status": None} if name else None

    def create_doc(self, emp, period, user):
        self.created.append(user)
        return "NEWDOC"

    def write_weights(self, target, weights, stage):
        self.writes.append((target, stage, dict(weights)))
        return "BW-1"

    def pending_for(self, user):
        return {"BW-1": 1} if self.pending_after else {}

    def full_name(self, u):
        return "Hoan"

    def notify(self, *a):
        self.notes.append(a)


class _Proxy:
    def __init__(self, ok=True):
        self.ok = ok

    def check(self, actor, m, status):
        self.seen = status
        return (True, "", False) if self.ok else (False, "khong duoc", False)


class Submit(unittest.TestCase):
    def setUp(self):
        ENGINE.calls.clear()
        SERVICE.submit_on_behalf = lambda name, actor: (SERVICE.submitted.append((name, actor)), "REQ-1")[1]
        SERVICE.submitted.clear()

    def test_nop_thay_tao_phieu_cho_nhan_vien_roi_duyet_buoc_cua_minh(self):
        r = FakeRepo()
        out = ts.ProxySubmitService(r, _Proxy()).execute(LEAD, "EMP-1", "2026-09", {"B1": 60, "B2": 40})
        self.assertEqual(r.created, [EMP])  # requester la chinh nhan vien
        self.assertEqual([w[1] for w in r.writes], ["submit", "lead"])
        self.assertEqual(SERVICE.submitted, [("BW-1", LEAD)])
        self.assertEqual(ENGINE.calls, [("approve", "REQ-1", LEAD)])
        self.assertEqual(len(r.notes), 1)
        self.assertEqual(r.notes[0][0], EMP)
        self.assertEqual(out, {"name": "BW-1", "final": False})

    def test_khong_duoc_phep_thi_khong_ghi_gi(self):
        r = FakeRepo()
        with self.assertRaises(Throw):
            ts.ProxySubmitService(r, _Proxy(ok=False)).execute(A, "EMP-1", "2026-09", {"B1": 100})
        self.assertEqual((r.writes, SERVICE.submitted, ENGINE.calls), ([], [], []))

    def test_phieu_khong_ve_tay_minh_thi_bao_loi_de_rollback(self):
        r = FakeRepo(pending_after=False)
        with self.assertRaises(Throw):
            ts.ProxySubmitService(r, _Proxy()).execute(LEAD, "EMP-1", "2026-09", {"B1": 100})
        self.assertEqual(ENGINE.calls, [])

    def test_brand_ngung_hoat_dong_bi_chan(self):
        with self.assertRaises(Throw):
            ts.ProxySubmitService(FakeRepo(), _Proxy()).execute(LEAD, "EMP-1", "2026-09", {"OLD": 100})

    def test_phieu_nhap_co_san_thi_dung_lai(self):
        r = FakeRepo(existing="BW-1", final=True)
        p = _Proxy()
        out = ts.ProxySubmitService(r, p).execute(LEAD, "EMP-1", "2026-09", {"B1": 100})
        self.assertEqual(p.seen, "draft")
        self.assertEqual(r.created, [])
        self.assertTrue(out["final"])


class Page(unittest.TestCase):
    def test_trang_co_nut_nop_thay_goi_dung_api(self):
        with open(os.path.join(FEAT, "ui", "main_section.html"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('call("proxy_weights"', src)
        self.assertIn('data-act="proxy-submit"', src)
        self.assertIn("if (!m.actionable && m.can_proxy) return proxyPanel(m);", src)
        with open(os.path.join(FEAT, "controllers", "api.py"), encoding="utf-8") as fh:
            self.assertIn("def proxy_weights(employee: str, period: str, weights: str):", fh.read())


if __name__ == "__main__":
    unittest.main()
