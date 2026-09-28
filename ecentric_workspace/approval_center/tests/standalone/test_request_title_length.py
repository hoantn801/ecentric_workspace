"""Tieu de phieu (request_title) dai toi 255 ky tu tren MOI form (28/09/2026).

EC-PAYR-2026-00272: tieu de 150 ky tu ("Chi phi su dung lai hinh anh ... hop dong so
02022026/HDDV/ECENTRIC-DNHB") -> "Value too big ... max 140". 27/29 form de mac dinh Data
(140) trong khi 15 form cho go 180 o giao dien - loi nam san, chi cho tieu de du dai.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_request_title_length.py
"""
import glob
import io
import json
import os
import re
import sys
import types

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MAX = 255


def _doctypes():
    out = {}
    for p in glob.glob(os.path.join(_ROOT, "**", "doctype", "*", "*.json"), recursive=True):
        try:
            d = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("doctype") == "DocType":
            for f in d.get("fields", []):
                if f.get("fieldname") == "request_title" and f.get("fieldtype") == "Data":
                    out[d["name"]] = (p, d, f)
    return out


def test_moi_request_title_la_255():
    dts = _doctypes()
    assert len(dts) >= 29
    thieu = {n: f.get("length") for n, (_p, _d, f) in dts.items() if f.get("length") != MAX}
    assert not thieu, "request_title chua 255: %s" % thieu


def test_giao_dien_khong_cho_go_dai_hon_db():
    for p in glob.glob(os.path.join(_ROOT, "approval_center", "features", "*", "ui", "main_section.html")):
        s = io.open(p, encoding="utf-8").read()
        for m in re.finditer(r'<input[^>]*data-model="request_title"[^>]*>', s):
            ml = re.search(r'maxlength="(\d+)"', m.group(0))
            if ml:
                assert int(ml.group(1)) <= MAX, p


def _events(inserted):
    fr = types.ModuleType("frappe")

    class Doc(dict):
        def insert(self, ignore_permissions=False):
            if len(self.get("title") or "") > 140:
                raise ValueError("Value too big")
            inserted.append(dict(self))
            self.name = "D1"
            return self
    fr.get_doc = lambda d: Doc(d)
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    res = types.ModuleType("ecentric_workspace.notification_center.resolvers")
    res.resolve_notification = lambda *a, **k: {}
    mods = {"frappe": fr, "ecentric_workspace": types.ModuleType("e"),
            "ecentric_workspace.notification_center": types.ModuleType("n"),
            "ecentric_workspace.notification_center.resolvers": res}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        mod = types.ModuleType("_events_rieng")
        path = os.path.join(_ROOT, "notification_center", "events.py")
        exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


@pytest.mark.parametrize("n", [50, 140, 141, 255, 300])
def test_thong_bao_teams_khong_bi_nuot_vi_tieu_de_dai(n):
    got = []
    ev = _events(got)
    title = "Cần duyệt: " + "x" * n
    assert ev._delivery("e1", "u@x", "teams", "Pending", title=title, dedupe_key="k") == "D1"
    assert len(got[0]["title"]) <= 140
    if len(title) <= 140:
        assert got[0]["title"] == title
    else:
        assert got[0]["title"].endswith("…") and got[0]["title"][:139] == title[:139]
