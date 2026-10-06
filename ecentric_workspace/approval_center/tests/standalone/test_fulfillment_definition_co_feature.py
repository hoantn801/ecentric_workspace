"""Moi loai phieu co buoc xu ly PHAI khai `feature=` trong ApprovalDefinition (05/10/2026).

Daily Target quen dong do -> fulfillment_service.claim dung duong dan module rong va nem
"No module named 'ecentric_workspace.approval_center.features.'" khi nhan xu ly tu popup trang
Tat ca yeu cau (trang form rieng khong loi vi di duong khac - nen khong ai thay).
"""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[2]


def test_moi_doctype_co_buoc_xu_ly_deu_khai_feature():
    tr = (APP / "shared/workflow/transitions.py").read_text(encoding="utf-8")
    block = re.search(r'FULFILLMENT_DOCTYPES = \((.*?)"\)', tr, re.S).group(1) + '"'
    doctypes = re.findall(r'"(EC [^"]+)"', block)
    assert "EC Daily Target Request" in doctypes and len(doctypes) >= 10
    for dt in doctypes:
        hits = [p for p in (APP / "features").glob("*/domain/definition.py")
                if '"%s"' % dt in p.read_text(encoding="utf-8")]
        assert hits, dt
        src = hits[0].read_text(encoding="utf-8")
        assert re.search(r"\bfeature\s*=\s*(feature|\"[a-z_]+\")", src), "%s thieu feature= (%s)" % (dt, hits[0])
