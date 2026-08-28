# Copyright (c) 2026, eCentric and contributors
"""Ask the provider which transition applies. Do not configure it, and never guess it.

Captured from the eContract portal on 2026-08-28, after three nights of wrong diagnoses:

    GET /api/Workflow/{instanceId}?userid={userId}
      -> availableTransitions[{transitionId, processAction, signType, isSigned,
                               transitionType, toState, ...}]

The reason this matters is not convenience. In one real workflow the four "Phe duyet" edges
are -9, -10, -11 and -4 - no pattern - and the LAST one requires processAction
WfFunctionRunSignedA with signType ky-chinh while the others require
WfFunctionRunSignedOther with ky-tham-gia. Our design held ONE configured value per stage,
so it was wrong on at least one step of every document, and the failure mode was a bare
"Duong chuyen khong hop le" that cost a whole night to attribute.

The signature-type check exists because of a second thing the same portal test showed:
Hoan approved all four steps by hand and the "Ky chinh" box still read "Chua co". The
workflow completed; the main signature was never applied; nothing said so.
"""
import sys
import types
import unittest


def _stub_frappe():
    """next_handler nhap frappe o cap module. Bo test standalone chay ngoai Frappe nen dung
    stub toi thieu - CHI de nhap duoc; moi phep kiem duoi day khong cham vao DB."""
    if "frappe" in sys.modules:
        return
    fr = types.ModuleType("frappe")
    fr.conf = {}
    fr.db = types.SimpleNamespace(get_value=lambda *a, **k: None,
                                  get_all=lambda *a, **k: [])
    fr.get_all = lambda *a, **k: []
    fr.get_doc = lambda *a, **k: None
    fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception("throw"))
    fr._ = lambda x: x
    sys.modules["frappe"] = fr


_stub_frappe()

from ecentric_workspace.platform.esign import next_handler as nh   # noqa: E402


class _Adapter:
    def __init__(self, transitions=None, raises=None):
        self._t = transitions or []
        self._raises = raises

    def available_transitions(self, instance_id, provider_user_id):
        if self._raises:
            raise self._raises
        return self._t


APPROVE = {"transition_id": "-4", "transition_name": "Phê duyệt",
           "process_action": "WfFunctionRunSignedA", "sign_type": "ky-chinh",
           "requires_signature": True, "transition_type": "approve", "terminal": True}
REJECT = {"transition_id": "-7", "transition_name": "Từ chối",
          "process_action": "", "sign_type": "", "requires_signature": False,
          "transition_type": "normal", "terminal": False}


class TestDiscovery(unittest.TestCase):
    def test_picks_the_approve_edge(self):
        cfg, why = nh.discover_transition(_Adapter([REJECT, APPROVE]), "doc", "user")
        self.assertIsNone(why)
        self.assertEqual(cfg["transition_id"], "-4")
        self.assertEqual(cfg["process_action"], "WfFunctionRunSignedA")
        self.assertEqual(cfg["sign_type"], "ky-chinh")

    def test_never_falls_back_to_the_first_edge(self):
        """Canh con lai tren trang thai nay la 'Tu choi'. Lay bua = tu choi chung tu."""
        cfg, why = nh.discover_transition(_Adapter([REJECT]), "doc", "user")
        self.assertIsNone(cfg)
        self.assertIn("no_approve_transition", why)
        self.assertIn("Từ chối", why)

    def test_two_ways_forward_is_refused_not_guessed(self):
        other = dict(APPROVE, transition_id="-5")
        cfg, why = nh.discover_transition(_Adapter([APPROVE, other]), "doc", "user")
        self.assertIsNone(cfg)
        self.assertIn("ambiguous_approve_transition", why)

    def test_empty_list_is_refused(self):
        cfg, why = nh.discover_transition(_Adapter([]), "doc", "user")
        self.assertIsNone(cfg)
        self.assertEqual(why, "no_available_transition")

    def test_a_failed_call_reports_WHAT_went_wrong(self):
        """Ghi ten loai loi thoi la chua du.

        Lan chay that 28/08 tra ve dung mot chu "SctsHttpError": biet la hong, khong biet ma
        trang thai, khong biet provider noi gi - lai phai doan. Dung cai sai da ton hai dem.
        """
        cfg, why = nh.discover_transition(
            _Adapter(raises=RuntimeError("HTTP 404 workflow instance not found")), "doc", "user")
        self.assertIsNone(cfg)
        self.assertIn("transition_discovery_failed", why)
        self.assertIn("404", why, "phai mang theo noi dung loi, khong chi ten loai")
        self.assertIn("workflow instance not found", why)


class TestRefusalVersusUnreachable(unittest.TestCase):
    """Hai chuyen khac han nhau, va phai xu ly khac nhau.

    - Nha cung cap NOI ro khong duoc di (khong co canh approve, hai canh, thieu metadata)
      -> dung lai. Lay cau hinh cu ra dung thay la di nguoc lai dieu ho vua noi.
    - KHONG HOI DUOC (mang loi, 4xx) -> chua biet gi ca, van con cau hinh tren ho so lam
      duong lui. Lan chay 28/08 rot thang ve pool vi mot loi HTTP, va SCTS gui cho BAY nguoi.
    """

    def test_provider_refusals_are_refusals(self):
        for why in ("no_available_transition", "no_approve_transition:Từ chối",
                    "ambiguous_approve_transition:-4,-5", "incomplete_transition:-4"):
            self.assertTrue(nh.why_is_refusal(why), why)

    def test_an_unreachable_provider_is_not_a_refusal(self):
        for why in ("transition_discovery_failed:SctsHttpError: HTTP 404",
                    "adapter_cannot_discover_transitions"):
            self.assertFalse(nh.why_is_refusal(why), why)

    def test_nothing_is_a_refusal_by_default(self):
        self.assertFalse(nh.why_is_refusal(None))
        self.assertFalse(nh.why_is_refusal(""))

    def test_incomplete_metadata_is_refused(self):
        bad = dict(APPROVE, process_action="")
        cfg, why = nh.discover_transition(_Adapter([bad]), "doc", "user")
        self.assertIsNone(cfg)
        self.assertIn("incomplete_transition", why)

    def test_an_adapter_without_the_call_says_so(self):
        cfg, why = nh.discover_transition(object(), "doc", "user")
        self.assertIsNone(cfg)
        self.assertEqual(why, "adapter_cannot_discover_transitions")


class TestSignatureTypeGuard(unittest.TestCase):
    def test_matching_type_passes(self):
        self.assertTrue(nh.signature_type_matches("ky-chinh", "ky-chinh"))
        self.assertTrue(nh.signature_type_matches("KY-CHINH", " ky-chinh "))

    def test_wrong_type_is_refused(self):
        """Cai nay chinh la o 'Ky chinh' bi bo trong ma khong ai bao."""
        self.assertFalse(nh.signature_type_matches("ky-chinh", "ky-tham-gia"))

    def test_missing_type_on_our_side_is_refused(self):
        self.assertFalse(nh.signature_type_matches("ky-chinh", None))

    def test_a_transition_that_states_no_requirement_is_not_blocked(self):
        self.assertTrue(nh.signature_type_matches("", "ky-tham-gia"))
        self.assertTrue(nh.signature_type_matches(None, None))


class TestTargetedHandoverIsOnWithAWorkingKillSwitch(unittest.TestCase):
    """Mac dinh BAT tu chieu 28/08, va cong tat khan cap phai thuc su tat.

    Sang 28/08 duong nay bi TAT: lan duy nhat eContract nhan thanh cong lenh transition
    (EC-PAYR-2026-00032), chung tu ket cung - trang thai "Cho gui di", khong dong workflow,
    khong chu ky, khong con nut "Xu ly" cho chinh nguoi duoc chi dinh.

    Chieu cung ngay co capture lenh "Xu ly" cua CHINH portal tren mot chung tu do ERP tao
    ra, va no thanh cong. Doi chieu tung truong: hinh dang payload giong het, cau hinh bac
    nguoi trinh trung tung chu. Bien so duy nhat tim duoc la signatureInfo.name (ten hien
    thi vs ma) - da sua.

    Can can nghieng lai vi duong lui khong con trung lap: no dang BAO DAM phat cho ca 7
    truong bo phan. Nhung phai giu duoc duong tat: mot lenh `bench set-config ... 0` la ve
    lai trang thai dang chay duoc, khong can deploy.
    """

    def setUp(self):
        # Dat tren CHINH module ma next_handler dang giu tham chieu. Mot bo test khac cai mot
        # stub frappe rieng vao sys.modules, nen `import frappe` o day co the ra module KHAC -
        # va phep kiem se doc mot cau hinh khong ai dung.
        self._old = dict(getattr(nh.frappe, "conf", {}) or {})

    def tearDown(self):
        nh.frappe.conf = self._old

    def test_on_when_the_flag_is_absent(self):
        nh.frappe.conf = {}
        self.assertTrue(nh.targeted_handover_enabled())

    def test_the_kill_switch_really_kills(self):
        for off in (0, "0", "false", "False", "no", "off", "OFF"):
            nh.frappe.conf = {"ec_esign_targeted_handover": off}
            self.assertFalse(nh.targeted_handover_enabled(),
                             "gia tri %r phai TAT duong nay" % (off,))

    def test_explicit_one_is_on(self):
        nh.frappe.conf = {"ec_esign_targeted_handover": 1}
        self.assertTrue(nh.targeted_handover_enabled())

    def test_an_empty_value_is_not_a_kill_switch(self):
        """Cau hinh de trong la "chua dat", khong phai "tat"."""
        for blank in (None, ""):
            nh.frappe.conf = {"ec_esign_targeted_handover": blank}
            self.assertTrue(nh.targeted_handover_enabled())

    def test_pool_is_still_reachable_when_switched_off(self):
        nh.frappe.conf = {"ec_esign_targeted_handover": 0}
        plan = nh.plan_handover({}, "prof", "UAT", stage="requester",
                                adapter=_Adapter([APPROVE]), instance_id="doc")
        self.assertEqual(plan["mode"], "pool")
        self.assertEqual(plan["reason"], "targeted_handover_disabled")



if __name__ == "__main__":
    unittest.main()
