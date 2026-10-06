"""feature_of(code) tra dung thu muc feature cho MOI loai phieu da dang ky (06/10/2026) - duyet
nhanh goi controller qua duong nay; thieu mot loai la loai do khong duyet nhanh duoc.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_feature_of_moi_loai.py
"""
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[4]
APP = ROOT / "ecentric_workspace"


def test_moi_loai_phieu_co_feature_va_controller():
    if "frappe" not in sys.modules:
        fr = types.ModuleType("frappe")
        fr._ = lambda s: s
        sys.modules["frappe"] = fr
    sys.path.insert(0, str(ROOT))
    for k in [k for k in sys.modules if k.startswith("ecentric_workspace")]:
        del sys.modules[k]
    from ecentric_workspace.approval_center.shared import registry as r
    assert len(r.APPROVAL_DEFINITIONS) >= 32
    for code in r.APPROVAL_DEFINITIONS:
        f = r.feature_of(code)
        assert f, code
        assert (APP / "approval_center" / "features" / f / "controllers" / "api.py").exists(), (code, f)
    assert r.feature_of("LEAVE_REQUEST") == "leave"
