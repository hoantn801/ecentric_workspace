"""Moi loai phieu tu khai quick_summary (06/10/2026): 1-5 truong, truong co that trong DocType,
KHONG co truong luong ca nhan.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_quick_summary_khai_bao.py
"""
import ast
import json
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[2]
SALARY = ("salary", "luong", "incentive", "total_bonus", "gross")


def _decls():
    out = {}
    for p in sorted((APP / "features").glob("*/domain/definition.py")):
        src = p.read_text(encoding="utf-8")
        m = re.search(r"quick_summary=\((.*?)\n    \),", src, re.S)
        dt = re.search(r'"(EC [A-Za-z ]+?)"', src.replace('"EC AI Tool"', "")).group(1)
        out[p.parent.parent.name] = (dt, ast.literal_eval("(" + m.group(1).rstrip().rstrip(",") + ",)") if m else ())
    return out


def test_moi_loai_phieu_deu_khai_va_hop_le():
    decls = _decls()
    assert len(decls) >= 32
    for feature, (dt, pairs) in decls.items():
        assert 1 <= len(pairs) <= 5, feature
        slug = dt.lower().replace(" ", "_")
        meta = json.loads((APP / "doctype" / slug / (slug + ".json")).read_text(encoding="utf-8"))
        fields = {f["fieldname"] for f in meta["fields"]}
        for label, field in pairs:
            assert label and field in fields, "%s: %s khong co trong %s" % (feature, field, dt)
            assert not any(s in field.lower() for s in SALARY), "%s lo luong: %s" % (feature, field)
