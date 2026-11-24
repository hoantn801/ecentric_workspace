# Copyright (c) 2026, eCentric and contributors
"""p541: dung 5 don, khong 00002, tat thong bao trong luc chay va TRA LAI sau, duyet thay toi Approved."""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATCH = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "patches", "p541_tao_bu_clearance_im_lang.py")


def _nap():
    db = {"EC Resignation Request": {n: {"withdrawn_at": None} for n in
                                     ["EC-RESN-2026-0000%d" % i for i in (2, 3, 4, 5, 6, 8)]},
          "EC Clearance Request": {}, "EC Approval Request": {}, "ToDo": {}}
    db["EC Resignation Request"]["EC-RESN-2026-00006"]["withdrawn_at"] = "x"
    f = types.ModuleType("frappe")
    f.flags = types.SimpleNamespace(mute_emails=False)

    def get_value(dt, flt, fld, as_dict=False):
        rows = db.get(dt, {})
        if isinstance(flt, dict):
            hit = [n for n, r in rows.items() if all(r.get(k) == v for k, v in flt.items())]
            if not hit:
                return None
            flt = hit[0]
        r = rows.get(flt)
        if r is None:
            return None
        if isinstance(fld, list):
            return types.SimpleNamespace(**{k: (flt if k == "name" else r.get(k)) for k in fld})
        return r.get(fld)

    def set_value(dt, n, fld, v, **k):
        db[dt][n][fld] = v

    f.db = types.SimpleNamespace(exists=lambda dt, n: n in db.get(dt, {}), get_value=get_value,
                                 set_value=set_value, commit=lambda: None)
    f.get_all = lambda dt, filters=None, pluck=None: [n for n, r in db.get(dt, {}).items()
                                                      if all(r.get(k) == v for k, v in filters.items())]
    goi = {"pub": [], "tao": [], "duyet": []}
    ncev = types.ModuleType("ev")
    goc = lambda *a, **k: goi["pub"].append(a)
    ncev.publish_notification_event = goc

    def tao(don):
        n = "CLR-" + don[-2:]
        db["EC Clearance Request"][n] = {"resignation_request": don, "approval_request": "AR-" + n}
        db["EC Approval Request"]["AR-" + n] = {"approval_status": "Pending", "lv": 2}
        db["ToDo"]["T-" + n] = {"reference_type": "EC Clearance Request", "reference_name": n, "status": "Open"}
        ncev.publish_notification_event("x")
        goi["tao"].append(don)
        return n

    def duyet(req, actor=None, reason=None):
        assert reason and actor == "Administrator"
        r = db["EC Approval Request"][req]
        r["lv"] -= 1
        ncev.publish_notification_event("y")
        if r["lv"] <= 0:
            r["approval_status"] = "Approved"
        goi["duyet"].append(req)

    svc = types.SimpleNamespace(create_from_resignation=tao)
    eng = types.SimpleNamespace(admin_override_current_level=duyet)
    mods = {"frappe": f, "ecentric_workspace.notification_center": types.SimpleNamespace(events=ncev),
            "ecentric_workspace.notification_center.events": ncev,
            "ecentric_workspace.approval_center.shared.workflow": types.SimpleNamespace(transitions=eng),
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.features.clearance_request.application":
                types.SimpleNamespace(service=svc),
            "ecentric_workspace.approval_center.features.clearance_request.application.service": svc}
    for k in ("ecentric_workspace", "ecentric_workspace.approval_center",
              "ecentric_workspace.approval_center.shared", "ecentric_workspace.approval_center.features",
              "ecentric_workspace.approval_center.features.clearance_request"):
        mods.setdefault(k, types.ModuleType(k))
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    m = types.ModuleType("p541")
    exec(compile(io.open(_PATCH, encoding="utf-8").read(), _PATCH, "exec"), m.__dict__)
    return m, db, goi, ncev, goc, f, saved


class T(unittest.TestCase):
    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_chay(self):
        m, db, goi, ncev, goc, f, self.saved = _nap()
        self.assertNotIn("EC-RESN-2026-00002", m.DON)
        m.execute()
        self.assertEqual(goi["tao"], ["EC-RESN-2026-00003", "EC-RESN-2026-00004", "EC-RESN-2026-00005",
                                      "EC-RESN-2026-00008"])                 # 00006 da rut
        self.assertEqual(goi["pub"], [], "khong duoc gui thong bao nao")
        self.assertIs(ncev.publish_notification_event, goc, "phai tra lai ham thong bao")
        self.assertFalse(f.flags.mute_emails)
        for n, r in db["EC Approval Request"].items():
            self.assertEqual(r["approval_status"], "Approved", n)
        self.assertTrue(all(t["status"] == "Closed" for t in db["ToDo"].values()))
        m.execute()                                                           # idempotent
        self.assertEqual(len(goi["tao"]), 4)


if __name__ == "__main__":
    unittest.main()
