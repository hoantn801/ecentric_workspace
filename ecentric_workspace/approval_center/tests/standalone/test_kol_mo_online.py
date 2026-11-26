# Copyright (c) 2026, eCentric and contributors
"""PO 26/11/2026: hop dong KOL - mo / sua ban DU tren Word Online (SharePoint thu muc han che).

Chi nhom `kol_access.can_download_full` (nguoi lap SAU khi gui, Ke toan, System Manager, nguoi tao
creator, ky so nhap) mo duoc. Nguoi duyet khac (Truong phong, CEO...), CC, nguoi theo doi: chi ban che.
Moi lan mo ghi vet nhu tai ban du; chua co ban SharePoint -> bao ro "dung Tai ve"; endpoint chi POST.

    python3 -m pytest -q ecentric_workspace/approval_center/tests/standalone/test_kol_mo_online.py
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_po_17_11 import CR, STATE, Throw, _access, _kol, _read  # noqa: E402

MIRROR_MOD = "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror"
HD = "/private/files/HDDV_26112026_ab12cd34.docx"
SHARE = "https://sp/share/abc"
WEB = "https://sp/KOL/CR-1/HDDV.docx"


class _FakeMirror(types.ModuleType):
    """`sharepoint_mirror.url_mo_online` gia: ghi lai loi goi, tra link theo bang."""

    def __init__(self, links):
        super().__init__(MIRROR_MOD)
        self.links, self.calls = links, []

    def url_mo_online(self, dt, name, file_url, user):
        self.calls.append((dt, name, file_url, user))
        if isinstance(self.links, Exception):
            raise self.links
        return self.links.get(file_url)


def _setup(user="fin@ec", links=None, can_view=lambda doc, u: True, **kw):
    a = _access(user)
    fr = sys.modules["frappe"]
    m = _FakeMirror({HD: WEB} if links is None else links)
    pkg_name = MIRROR_MOD.rsplit(".", 1)[0]
    import importlib
    pkg = importlib.import_module(pkg_name)
    cu = (sys.modules.get(MIRROR_MOD), getattr(pkg, "sharepoint_mirror", None))
    sys.modules[MIRROR_MOD] = m
    pkg.sharepoint_mirror = m

    def _restore():
        if cu[0] is None:
            sys.modules.pop(MIRROR_MOD, None)
        else:
            sys.modules[MIRROR_MOD] = cu[0]
        if cu[1] is None:
            if hasattr(pkg, "sharepoint_mirror"):
                delattr(pkg, "sharepoint_mirror")
        else:
            pkg.sharepoint_mirror = cu[1]
    STATE["exists"].add(("File", tuple(sorted({"file_url": HD, "attached_to_doctype": CR,
                                                "attached_to_name": "CR-1"}.items()))))
    logs = []
    import frappe.core.doctype.access_log.access_log as al  # noqa  (gia ben duoi)
    al.make_access_log = lambda **k: logs.append(k)
    a._can_view = can_view
    d = _kol(contract_file=HD, owner="req@ec", **kw)
    return a, fr, m, d, logs, _restore


def _fake_access_log():
    for n in ("frappe.core", "frappe.core.doctype", "frappe.core.doctype.access_log",
              "frappe.core.doctype.access_log.access_log"):
        sys.modules.setdefault(n, types.ModuleType(n))


class _Base(unittest.TestCase):
    def setUp(self):
        _fake_access_log()
        self._restores = []

    def tearDown(self):
        for r in self._restores:
            r()

    def mk(self, *a, **k):
        r = _setup(*a, **k)
        self._restores.append(r[-1])
        return r[:-1]


class AiMoDuoc(_Base):
    def test_ke_toan_mo_duoc_tra_url_va_ghi_vet(self):
        a, _fr, m, _d, logs = self.mk("fin@ec")
        self.assertEqual(a.open_online("CR-1", None, "fin@ec"), {"url": WEB})
        self.assertEqual(m.calls, [(CR, "CR-1", HD, "fin@ec")])
        self.assertTrue(any("fin@ec" in c and "Word Online" in c and "hợp đồng" in c for c in STATE["comments"]))
        self.assertFalse(any("ab12cd34" in c for c in STATE["comments"]), "khong ghi ten / URL tep")
        self.assertEqual(logs, [], "phieu da gui: binh luan tren phieu la vet (nhu download_file)")

    def test_nguoi_lap_sau_khi_gui_mo_duoc(self):
        a, _fr, _m, _d, _l = self.mk("req@ec")
        self.assertEqual(a.open_online("CR-1", None, "req@ec")["url"], WEB)

    def test_nguoi_tao_creator_va_system_manager_mo_duoc(self):
        a, _fr, _m, _d, _l = self.mk("owner@ec")
        self.assertEqual(a.open_online("CR-1", None, "owner@ec")["url"], WEB)
        STATE["roles"]["sm@ec"] = ["System Manager"]
        self.assertEqual(a.open_online("CR-1", None, "sm@ec")["url"], WEB)

    def test_nhap_ky_so_ghi_access_log(self):
        a, _fr, _m, _d, logs = self.mk("req@ec", approval_request=None)
        a._esign_enabled = lambda name: True
        self.assertEqual(a.open_online("CR-1", None, "req@ec")["url"], WEB)
        self.assertEqual([x["method"] for x in logs], ["kol_open_online"])


class AiBiChan(_Base):
    def _chan(self, user, **kw):
        a, fr, m, _d, logs = self.mk(user, **kw)
        n = len(STATE["comments"])
        with self.assertRaises(fr.PermissionError) as cm:
            a.open_online("CR-1", None, user)
        self.assertIn("bản che", str(cm.exception))
        self.assertEqual(m.calls, [], "khong hoi link SharePoint khi khong co quyen")
        self.assertEqual((len(STATE["comments"]), logs), (n, []))

    def test_nguoi_duyet_truong_phong_ceo(self):
        self._chan("truongphong@ec")
        self._chan("ceo@ec")

    def test_cc_va_nguoi_theo_doi(self):
        self._chan("cc@ec")

    def test_nguoi_la(self):
        self._chan("la@ec")

    def test_nguoi_lap_khi_con_nhap_khong_ky_so(self):
        self._chan("req@ec", approval_request=None)

    def test_duoc_ban_du_nhung_khong_xem_duoc_phieu(self):
        self._chan("owner@ec", can_view=lambda doc, u: False)

    def test_phieu_khong_phai_kol(self):
        a, _fr, m, _d, _l = self.mk("fin@ec", contract_type="Sales / Bán ra (EC)")
        with self.assertRaises(Throw):
            a.open_online("CR-1", None, "fin@ec")
        self.assertEqual(m.calls, [])


class ChuaCoBanOnline(_Base):
    def test_chua_cau_hinh_hoac_chua_dong_bo_bao_ro(self):
        a, fr, _m, _d, logs = self.mk("fin@ec", links={})
        with self.assertRaises(Throw) as cm:
            a.open_online("CR-1", None, "fin@ec")
        self.assertNotIsInstance(cm.exception, fr.PermissionError)
        self.assertIn("chưa có bản online", str(cm.exception))
        self.assertIn("Tải về", str(cm.exception))
        self.assertEqual((STATE["comments"], logs), ([], []), "khong mo duoc thi khong ghi vet")

    def test_loi_doc_link_fail_closed(self):
        a, _fr, _m, _d, _l = self.mk("fin@ec", links=RuntimeError("db"))
        with self.assertRaises(Throw) as cm:
            a.open_online("CR-1", None, "fin@ec")
        self.assertIn("chưa có bản online", str(cm.exception))

    def test_tep_khong_gan_phieu_nay(self):
        a, _fr, m, _d, _l = self.mk("fin@ec", links={"/private/files/khac.docx": WEB})
        with self.assertRaises(Throw):
            a.open_online("CR-1", "/private/files/khac.docx", "fin@ec")
        self.assertEqual(m.calls, [])


class CoServer(_Base):
    """`can_open_online` (co nut tren trang) = can_download_full + co ban SharePoint."""

    def test_co(self):
        a, _fr, _m, d, _l = self.mk("fin@ec")
        self.assertTrue(a.can_open_online(d, "fin@ec"))
        self.assertTrue(a.can_open_online(d, "req@ec"))
        self.assertFalse(a.can_open_online(d, "truongphong@ec"))
        self.assertFalse(a.can_open_online(d, "cc@ec"))

    def test_chua_co_ban_sharepoint_thi_khong_co_nut(self):
        a, _fr, _m, d, _l = self.mk("fin@ec", links={})
        self.assertFalse(a.can_open_online(d, "fin@ec"))

    def test_nguoi_khong_duoc_khong_hoi_sharepoint(self):
        a, _fr, m, d, _l = self.mk("fin@ec")
        a.can_open_online(d, "truongphong@ec")
        self.assertEqual(m.calls, [])


class Noi(unittest.TestCase):
    def test_endpoint_chi_post_khong_nhan_user(self):
        api = _read("features/contract_review/controllers/kol_api.py")
        i = api.index("def kol_open_online(name, file_url=None):")
        self.assertIn('@frappe.whitelist(methods=["POST"])', api[api.rindex("\n@", 0, i) - 1:i])
        self.assertIn('_app("kol_access").open_online(name, file_url, _me())', api[i:i + 300])
        self.assertIn('"kol_open_online"', api[:api.index("def _app")])
        self.assertIn("kol_open_online)", _read("features/contract_review/controllers/api.py"))

    def test_co_tinh_o_server_cung_cho_can_download_full(self):
        src = _read("features/contract_review/application/kol_service.py")
        self.assertIn('"can_open_online": kol_access.can_open_online(business, user)', src)

    def test_kiem_quyen_truoc_khi_hoi_link(self):
        src = _read("features/contract_review/application/kol_access.py")
        i = src.index("def open_online(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertLess(body.index("can_download_full(doc, user) and _can_view(doc, user)"), body.index("online_url("))
        self.assertLess(body.index("online_url("), body.index("add_comment"))

    def test_trang_nut_theo_co_server_goi_post(self):
        html = _read("features/contract_review/ui/main_section.html")
        self.assertIn('if(x.can_open_online) dlH+=', html)
        self.assertIn('call("kol_open_online",{name:name})', html)
        self.assertIn('window.open(u,"_blank","noopener")', html)

    def test_patch_resync_va_manifest(self):
        import hashlib
        import json
        app = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        self.assertTrue(open(os.path.join(app, "patches.txt"), encoding="utf-8").read().rstrip().endswith(
            "ecentric_workspace.approval_center.patches.p570_resync_contract_review_mo_online_kol"))
        man = json.load(open(os.path.join(app, "approval_center/patches/resync_manifest.json"), encoding="utf-8"))
        ent = man["approval_center/features/contract_review/ui/main_section.html"]
        self.assertEqual(ent["last_resync_patch"], "p570_resync_contract_review_mo_online_kol")
        sha = hashlib.sha256(open(os.path.join(app, "approval_center/features/contract_review/ui/main_section.html"),
                                  "rb").read()).hexdigest()
        self.assertEqual(ent["sha256"], sha)


if __name__ == "__main__":
    unittest.main()
