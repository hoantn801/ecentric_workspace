"""[Chép từ app – _chung_ban_quyen/tests/test_issuer.py, 17/11/2026; chỉ đổi đường import cho ERP.]
Bộ cấp license phía máy chủ: token cấp ra phải được CHÍNH launcher / module kiểm của từng app nhận (khoá thử, không dùng khoá thật)."""
import base64
import importlib
import json
import os
import sys
import types
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parents[1]
SRC = HERE.parent
# ERP (17/11): bo cap license nam o domain/ec_license_issuer.py (khop tung byte voi ban app). Ma launcher / ec_online
# khong co tren ERP -> cac test can chung tu bo qua; test luat duyet van phai qua.
from ecentric_workspace.ai_tools.features.ai_live.domain import ec_license_issuer as I  # noqa: E402

try:
    import ec_online as O  # noqa: E402
except ImportError:
    O = None

PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIV_PEM = PRIV.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
PUB_PEM = PRIV.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
MK = os.urandom(32)
APP = os.urandom(32)
SECRET = {"mk": I._b64u_e(MK), "app_secret": I._b64u_e(APP), "rsa_private_pem": PRIV_PEM,
          "premium_fernet_key": Fernet.generate_key().decode()}
PARTS = {"guid": "GUID-1", "disk": "12345", "macs": ["aaaaaaaaaaaa"]}


def load_launcher(dirpath: Path):
    cfg = types.ModuleType("_build_cfg")
    cfg.APP_SECRET_B64 = base64.b64encode(APP).decode()
    cfg.PUBLIC_KEY_PEM = PUB_PEM
    cfg.BUILD_ID = "t"
    sys.modules["_build_cfg"] = cfg
    for m in ("launcher", "protect_common", "ec_online"):
        sys.modules.pop(m, None)
    sys.path.insert(0, str(dirpath))
    try:
        return importlib.import_module("launcher")
    finally:
        sys.path.remove(str(dirpath))


def test_elive_issue_verified_by_launcher(monkeypatch):
    d = SRC / "eC Live" / "ec-live" / "bao_mat_ec" / "launcher"
    if not d.is_dir():
        pytest.skip("không có launcher eLive")
    L = load_launcher(d)
    monkeypatch.setattr(sys.modules["ec_online"], "machine_parts", lambda: dict(PARTS))
    hw = L.hwid()
    payload = L.online_payload(hw)
    ident = I.decode_request("elive", payload)
    tok = I.issue("elive", SECRET, ident, "May A")
    data = L.verify_token(tok, hw)
    assert sys.modules["protect_common"].unwrap_mk(data["code_key"], APP, hw) == MK
    with pytest.raises(I.RequestError):
        I.decode_request("elive", dict(payload, hw="0" * 32))  # mã yêu cầu không khớp hw


def test_esync_issue_verified_by_launcher(monkeypatch):
    d = SRC / "eSync" / "esync" / "bao_mat" / "launcher"
    if not d.is_dir():
        pytest.skip("không có launcher eSync")
    L = load_launcher(d)
    monkeypatch.setattr(sys.modules["ec_online"], "machine_parts", lambda: dict(PARTS))
    mid = "SYNC-AAAA-BBBB-CCCC-DDDD"
    hw = L.hwid()
    ident = I.decode_request("esync", L.online_payload(mid, hw))
    assert ident == {"hw": hw, "mid": mid}
    tok = I.issue("esync", SECRET, ident, "May A")
    data = L.verify_token(tok, mid, hw)
    assert sys.modules["protect_common"].unwrap_mk(data["model_key"], APP, hw) == MK
    with pytest.raises(I.RequestError):
        I.issue("esync", dict(SECRET, premium_fernet_key=""), ident)


def test_evoice_issue_verified_by_app(monkeypatch):
    vl = SRC / "eVoice" / "voice-lab"
    if not (vl / "secure").is_dir():
        pytest.skip("không có eVoice")
    sys.path.insert(0, str(vl))
    from secure import license as lic
    from secure import machineid
    ed = Ed25519PrivateKey.generate()
    raw_priv = ed.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    raw_pub = ed.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(lic, "VENDOR_PUBLIC_KEY", raw_pub)
    monkeypatch.setattr(lic, "APP_SECRET", APP)
    monkeypatch.setattr(lic, "_IS_PLACEHOLDER", False)
    monkeypatch.setenv("EVOICE_MACHINE_ID", "0123456789abcdef01234567")
    ev = {"private_key": base64.b64encode(raw_priv).decode(), "master_key": base64.b64encode(MK).decode(),
          "app_secret": base64.b64encode(APP).decode()}
    mid = machineid.machine_id()
    ident = I.decode_request("evoice", {"request_code": mid, "hw": mid})
    tok = I.issue("evoice", ev, ident, "May A")
    assert lic.verify(tok).master_key == MK


def test_same_machine_rules():
    a = {"guid_h": "g", "disk_h": "d", "mac_h": ["m1", "m2"]}
    assert I.same_machine(a, {"guid_h": "g", "disk_h": "d", "mac_h": ["m9"]})       # đổi card mạng
    assert I.same_machine(a, {"guid_h": "g", "disk_h": "X", "mac_h": ["m2"]})       # đổi ổ, giữ card
    assert not I.same_machine(a, {"guid_h": "g2", "disk_h": "d", "mac_h": ["m1"]})  # khác Windows
    assert not I.same_machine(a, {"guid_h": "g", "disk_h": "X", "mac_h": ["m9"]})   # đổi cả ổ lẫn card -> coi máy mới
    assert not I.same_machine({"guid_h": ""}, {"guid_h": ""})


def test_decide_rules():
    import time as _t
    from datetime import datetime, timezone, timedelta
    now = _t.time()
    fresh = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    D = {"dist_id": "D1", "created_at": fresh}
    owner = {"name": "MAY-ABC", "status": "approved"}
    assert I.decide({"status": "approved"}, {}, None)[0] == "issue"
    assert I.decide({"status": "blocked"}, {}, None)[0] == "blocked"
    assert I.decide({"status": "pending"}, {}, None)[0] == "pending"
    assert I.decide(None, D, None)[0] == "issue"                                      # máy đầu tiên của gói
    assert I.decide(None, dict(D, created_at=old), None)[0] == "pending"              # gói > 14 ngày mới kích hoạt
    d, why = I.decide(None, D, owner)
    assert d == "pending" and "MAY-ABC" in why                                       # bản chép
    assert I.decide(None, dict(D, kind="noi_bo"), owner)[0] == "issue"               # gói nội bộ
    assert I.decide(None, dict(D, kind="noi_bo"), owner, dist_count=10)[0] == "pending"   # quá số máy
    assert I.decide(None, dict(D, kind="noi_bo", created_at=(datetime.now(timezone.utc) - timedelta(days=40)).isoformat()), owner)[0] == "pending"
    assert I.decide(None, {}, None, ip="1.2.3.4", office_ips=["1.2.3.4"])[0] == "issue"
    assert I.decide(None, {}, None)[0] == "pending"                                  # gói cũ / chép tay


def test_decide_c1_known_machine_other_hw():
    import time as _t
    now = _t.time()
    fp = {"guid_h": "g", "disk_h": "d", "mac_h": ["m1"]}
    m = {"status": "approved", "fp": fp, "hw": {"elive": "H1"}}
    assert I.decide(m, {}, None, product="elive", hw="H1", fp=fp, now=now)[0] == "issue"      # cấp lại đúng mã cũ
    assert I.decide(m, {}, None, product="elive", hw="H2", fp=fp, now=now)[0] == "pending"    # giả fp, hw khác
    fp2 = {"guid_h": "g", "disk_h": "d2", "mac_h": ["m1"]}                                     # đổi ổ C:
    assert I.decide(m, {}, None, product="elive", hw="H2", fp=fp2, now=now)[0] == "issue"
    m2 = dict(m, reissued_at={"elive": now - 86400})
    assert I.decide(m2, {}, None, product="elive", hw="H3", fp=fp2, now=now)[0] == "pending"  # lần 2 trong 30 ngày
    assert I.decide(dict(m, hw={}), {}, None, product="esync", hw="X", fp=fp, now=now)[0] == "issue"  # chưa biết hw sp này


def test_match_machine_prefers_approved():
    fp = {"guid_h": "g", "disk_h": "d", "mac_h": []}
    ms = [{"name": "p", "fp": fp, "status": "pending"}, {"name": "a", "fp": fp, "status": "approved"}]
    assert I.match_machine(ms, fp)["name"] == "a"
    assert I.match_machine(ms, {"guid_h": "z", "disk_h": "d"}) is None


def test_payload_fp_consistent_across_products():
    if O is None:
        pytest.skip("không có ec_online (mã app) trên ERP")
    # eLive / eSync / eVoice cùng 1 máy -> fp giống hệt (1 bản ghi máy cho cả 3 app)
    assert O.fp_report(PARTS) == O.fp_report(dict(PARTS))


def test_verify_dist_signature():
    import hashlib
    import hmac as _h
    key = "ab" * 32
    d = {"dist_id": "6f1c2a3b-0000-4000-8000-000000000001", "kind": "khach", "label": "máy Lix 2", "created_at": "2026-11-17T10:00:00Z"}
    d["sig"] = _h.new(key.encode(), I.dist_message(d), hashlib.sha256).hexdigest()
    assert I.verify_dist(d, key)["dist_id"] == d["dist_id"]
    assert I.verify_dist(dict(d, kind="noi_bo"), key) == {}      # sửa thành gói nội bộ -> chữ ký sai
    assert I.verify_dist(dict(d, dist_id="D2"), key) == {}       # tự bịa mã gói mới
    assert I.verify_dist(dict(d, sig=""), key) == {}
    assert I.verify_dist(d, "") == {}                            # ERP chưa có khoá -> không tin mã gói
    # bịa mã gói không chữ ký -> không còn là "máy đầu tiên của gói"
    assert I.decide(None, I.verify_dist({"dist_id": "FAKE"}, key), None)[0] == "pending"
    # T4: nhãn có "|" / dist_id không phải GUID / kind lạ -> không nhận
    g = "0f8fad5b-d9cb-469f-a165-70867728950e"
    for bad in ({"dist_id": g, "kind": "khach", "label": "a|b"}, {"dist_id": "D1", "kind": "khach", "label": ""},
                {"dist_id": g, "kind": "vip", "label": ""}):
        bad = dict(bad, created_at="2026-11-17T10:00:00Z")
        bad["sig"] = _h.new(key.encode(), I.dist_message(bad), hashlib.sha256).hexdigest()
        assert I.verify_dist(bad, key) == {}
    ok = {"dist_id": g, "kind": "khach", "label": "máy Lix", "created_at": "2026-11-17T10:00:00Z"}
    ok["sig"] = _h.new(key.encode(), I.dist_message(ok), hashlib.sha256).hexdigest()
    assert I.verify_dist(ok, key)["dist_id"] == g
