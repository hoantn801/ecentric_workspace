# Copyright (c) 2026, eCentric and contributors
"""PR-E QC 23/11: khoi Tai lieu & ky so tren form Hop dong.

  M2. document_setup_state dung CUNG bo loc dinh kem cua nghiep vu (definition.attachment_redactor)
      cho NGUOI DUYET - loai phieu khong khai (DNTT) -> khong loc; redactor loi -> an het tep cua
      nguoi khac (fail-closed). QC vong 2: NGUOI LAP khong bi loc (thay ca ban HDDV_ / tep
      Administrator giu); tep chinh nguoi xem tai len luon giu; chi KeyError = khong dang ky.
  M3. esign_enabled: khong co ho so BAT -> False; co ho so bat nhung phieu khong chon duoc ho so
      (vd khong_ky_cong) -> False; loi xac dinh theo phieu -> True (khong an nham).
"""
import ast
import io
import os
import sys
import textwrap
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_SRC = io.open(os.path.join(_APP, "ecentric_workspace", "platform", "esign", "document_setup.py"),
               encoding="utf-8").read()


def _fns(names):
    out = []
    for n in ast.parse(_SRC).body:
        if getattr(n, "name", None) in names:
            out.append(textwrap.dedent(ast.get_source_segment(_SRC, n)))
    assert len(out) == len(names), names
    return "\n\n".join(out)


class _D(dict):
    __getattr__ = dict.get


def _load(definition=None, raise_lookup=False, profiles_enabled=True, enabled_profile="P",
          profile_raises=False, user="duyet@x", requested_by="lap@x", lookup_exc=None):
    logs = []
    reg = types.ModuleType("reg")

    def get_definition_for_doctype(dt):
        if raise_lookup:
            raise KeyError(dt)
        if lookup_exc:
            raise lookup_exc
        return definition
    reg.get_definition_for_doctype = get_definition_for_doctype
    biz = _D(name="CTR-1", approval_request="AR-1")
    loaded = []

    def get_doc(dt, n):
        loaded.append(dt)
        return biz
    fk = types.SimpleNamespace(
        get_doc=get_doc, session=types.SimpleNamespace(user=user),
        log_error=lambda *a, **k: logs.append(a), get_traceback=lambda: "tb",
        db=types.SimpleNamespace(exists=lambda dt, f: profiles_enabled,
                                 get_value=lambda dt, n, f: "owner@x"))

    def gep(dt, code, bn):
        if profile_raises:
            raise RuntimeError("mo ho")
        return enabled_profile
    g = {"frappe": fk, "guard": types.SimpleNamespace(get_enabled_profile=gep),
         "perms": types.SimpleNamespace(business_requested_by=lambda bd, bn: requested_by)}
    key = "ecentric_workspace.approval_center.shared.registry"
    old = sys.modules.get(key)
    sys.modules[key] = reg
    exec(compile(_fns(["_is_requester", "_visible_file_names", "_esign_enabled"]), "ds", "exec"), g)

    def restore():
        if old is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = old
    g["_restore"], g["_logs"], g["_loaded"] = restore, logs, loaded
    return g


FILES = [_D(name="F1", file_name="HD.pdf", owner="lap@x"),
         _D(name="F2", file_name="HDDV_cccd.docx", owner="Administrator"),
         _D(name="F3", file_name="HDDV_ban_ky.pdf", owner="Administrator"),
         _D(name="F4", file_name="ghi_chu_duyet.pdf", owner="duyet@x")]


def _red_kol(atts, business, request):
    """Gia lap redactor KOL: an moi tep Administrator giu va ban HDDV_."""
    return [a for a in atts if a.get("owner") != "Administrator"
            and not str(a.get("file_name")).startswith("HDDV_")]


class TestVisible(unittest.TestCase):
    def test_khong_khai_redactor_thi_khong_loc(self):
        for kw in ({"raise_lookup": True}, {"definition": types.SimpleNamespace(attachment_redactor=None)}):
            g = _load(**kw)
            try:
                self.assertIsNone(g["_visible_file_names"]("EC Payment Request", "P-1", FILES))
            finally:
                g["_restore"]()

    def test_nguoi_duyet_dung_bo_loc_nghiep_vu(self):
        seen = []

        def red(atts, business, request):
            seen.append((len(atts), business.name, request))
            return _red_kol(atts, business, request)
        g = _load(definition=types.SimpleNamespace(attachment_redactor=red))
        try:
            self.assertEqual(g["_visible_file_names"]("EC Contract Review Request", "CTR-1", FILES),
                             {"F1", "F4"}, "nguoi duyet KHONG thay HDDV_ / tep Administrator giu")
            self.assertEqual(seen, [(4, "CTR-1", None)])
            self.assertNotIn("EC Approval Request", g["_loaded"], "khong nap AR")
        finally:
            g["_restore"]()

    def test_nguoi_lap_thay_tep_ky_cua_minh(self):
        g = _load(definition=types.SimpleNamespace(attachment_redactor=_red_kol), user="lap@x")
        try:
            self.assertIsNone(g["_visible_file_names"]("EC Contract Review Request", "CTR-1", FILES),
                              "nguoi lap: khong loc - thay HDDV_ban_ky.pdf (Administrator giu)")
        finally:
            g["_restore"]()

    def test_khong_cot_requested_by_thi_dung_owner(self):
        g = _load(definition=types.SimpleNamespace(attachment_redactor=_red_kol),
                  user="owner@x", requested_by=None)
        try:
            self.assertIsNone(g["_visible_file_names"]("EC Contract Review Request", "CTR-1", FILES))
        finally:
            g["_restore"]()

    def test_redactor_loi_chi_giu_tep_cua_minh(self):
        def red(*a):
            raise ValueError("x")
        g = _load(definition=types.SimpleNamespace(attachment_redactor=red))
        try:
            self.assertEqual(g["_visible_file_names"]("EC Contract Review Request", "CTR-1", FILES), {"F4"})
            self.assertEqual(len(g["_logs"]), 1)
        finally:
            g["_restore"]()

    def test_loi_registry_khac_keyerror_thi_an(self):
        g = _load(lookup_exc=ImportError("vo"))
        try:
            self.assertEqual(g["_visible_file_names"]("EC Contract Review Request", "CTR-1", FILES), set())
        finally:
            g["_restore"]()

    def test_tra_ve_dem_an_va_loc_truoc_vong(self):
        self.assertIn('"hidden_documents": len(all_groups) - len(groups)', _SRC)
        self.assertIn('"esign_enabled": _esign_enabled(business_doctype, business_name)', _SRC)
        self.assertIn("_stale_dsf(business_doctype, business_name, pkg_for_dsf,\n                                          all_groups)", _SRC)
        self.assertIn('"owner"', _SRC[_SRC.index("def _current_files"):_SRC.index("def _visible_file_names")])


class TestEnabled(unittest.TestCase):
    def _run(self, **kw):
        g = _load(definition=types.SimpleNamespace(code="Contract Review", attachment_redactor=None), **kw)
        try:
            return g["_esign_enabled"]("EC Contract Review Request", "CTR-1")
        finally:
            g["_restore"]()

    def test_khong_ho_so_bat(self):
        self.assertFalse(self._run(profiles_enabled=False))

    def test_phieu_khong_chon_duoc_ho_so(self):
        self.assertFalse(self._run(enabled_profile=None))

    def test_co_ho_so(self):
        self.assertTrue(self._run())

    def test_loi_xac_dinh_thi_khong_an(self):
        self.assertTrue(self._run(profile_raises=True))


if __name__ == "__main__":
    unittest.main()
