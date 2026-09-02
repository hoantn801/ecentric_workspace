# Copyright (c) 2026, eCentric and contributors
"""Hỏi nhà cung cấp nghĩ gì — mà không được ký hộ ai, và không được lộ dữ liệu ai.

Sự cố 02/09, EC-PAYR-2026-00041 / EC-DSP-2026-00028, chân ký EC-DSR-2026-00027:
`transition_with_recipients` bị trả 400 "Đường chuyển không hợp lệ hoặc không khớp trạng
thái", code lùi về `approve_and_sign` pool-wide, eContract trả 2xx kèm mã giao dịch — rồi
không tạo chữ ký nào và lịch sử workflow bên họ cũng không ghi nhận hành động nào. Hai đầu
đều báo "ổn", cái sai nằm Ở GIỮA. `provider_workflow_view` là con mắt nhìn vào khoảng giữa
đó.

Một công cụ chẩn đoán trên hồ sơ chi tiền có hai cách hỏng, và cả hai đều đã xảy ra thật
trong dự án này:

  1. nó GHI. Một endpoint "chỉ để xem" mà lỡ chạm vào đường gửi lệnh ký thì lần chẩn đoán
     tiếp theo sẽ tạo chữ ký THỨ HAI trên một chứng từ đã ký;
  2. nó ĐỔ DỮ LIỆU. Payload chân ký của eContract mang `user` (họ tên), `cccd`, `mobile`,
     `dob` nằm ngay cạnh `email` và `status` — "trả nguyên response cho nhanh" là biến một
     lệnh chẩn đoán thành một lệnh trích xuất nhân sự.

Và cách hỏng thứ ba, âm thầm nhất: NUỐT LỖI. Chính lớp `eligible_recipients` từng nuốt sạch
lỗi và trả None, nên lớp bảo vệ không chạy mà không ai biết vì sao. Một khối rỗng không kèm
lý do sẽ bị đọc thành "tài liệu này không có người ký nào" — đúng cái kết luận sai đã làm
mất hai đêm của tháng 8.
"""
import ast
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


_API = _read("platform", "esign", "api.py")
_FN_NAME = "provider_workflow_view"


def _segment(src, name):
    """Nguon THAT cua mot ham (KE CA decorator) hoac cua mot gan o cap module.

    Decorator phai nam trong doan cat: `@frappe.whitelist()` la mot nua cua cau tra loi
    "endpoint nay co phai chi doc khong". ast.FunctionDef.lineno tro vao dong `def`, nen lay
    them dong nho nhat trong decorator_list.
    """
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            return "\n".join(lines[start - 1:node.end_lineno])
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError("khong tim thay %r trong api.py" % name)


_SRC = "\n".join([_segment(_API, "_SAFE_SIGNER_KEYS"),
                  _segment(_API, "_MAX_PROBED_TRANSITIONS"),
                  _segment(_API, _FN_NAME)])


def _fn_node(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("khong tim thay ham %s" % name)


# --------------------------------------------------------------------------- ban gia
class _Boom(Exception):
    pass


class _State(object):
    """Dang cua NormalizedDocState, nhung chan ky la payload DAY DU cua eContract.

    Co y de nguyen ho ten / cccd / mobile / dob o day: neu endpoint chi "khong tra ra" nho
    viec ban chuan hoa da vut chung di tu truoc, thi bo loc cua endpoint chua bao gio duoc
    kiem — va ngay nao ban chuan hoa giu lai them mot truong la du lieu chay thang ra ngoai.
    """

    def __init__(self, status, signers, identity=None):
        self.status = status
        self.signers = signers
        self.identity = identity or {}
        self.files = []


NAME = "Nguyen Van Phuong"
CCCD = "079123456789"
MOBILE = "0909123456"
DOB = "1990-01-01"

SIGNER_PHUONG = {"id": "38445b30-5703-472f-8f92-832d77158d0f",
                 "role": "HOF", "role_text": "Ke toan truong",
                 "user": NAME, "email": "phuong.nguyen1@ecentric.vn",
                 "mobile": MOBILE, "cccd": CCCD, "dob": DOB,
                 "identityPlace": "Cuc CS QLHC ve TTXH", "identityDate": "2021-03-04",
                 "icon": "user.png", "rejectReason": None,
                 "sign_type": "ky-tham-gia", "signed_at": None, "is_external": False,
                 # eContract KHONG gui userId/signerId/signatureId tren dong nguoi ky - nen
                 # ban chuan hoa luon cho None. Doi soat chi con dua vao email.
                 "user_id": None, "signature_id": None, "status": "pending"}

SIGNER_HOAN = dict(SIGNER_PHUONG, id="73f72e15-4f56-4bde-84e9-68edd9918d7c",
                   role="REQ", role_text="Nguoi de nghi", user="Tran Van Hoan",
                   email="hoan.tran@ecentric.vn", status="signed", signed_at="2026-09-02 11:48:00")

APPROVE = {"transition_id": "-4", "transition_name": "Phê duyệt",
           "process_action": "WfFunctionRunSignedA", "sign_type": "ky-chinh",
           "requires_signature": True, "transition_type": "approve", "to_state": "S3",
           "terminal": False, "all_required": False}
REJECT = {"transition_id": "-7", "transition_name": "Từ chối", "process_action": "",
          "sign_type": "", "requires_signature": False, "transition_type": "normal",
          "to_state": "STOP", "terminal": True, "all_required": False}

_ALLOWED_ADAPTER_CALLS = {"poll_status", "available_transitions", "eligible_recipients"}


class _Adapter(object):
    def __init__(self, state=None, transitions=None, eligible=None,
                 poll_raises=None, transitions_raises=None):
        self._state = state
        self._transitions = transitions if transitions is not None else []
        #: tid -> set | None | Exception | ("none", "ly do") de mo phong dung hop dong that
        #: cua eligible_recipients: that bai thi GHI `_last_eligible_error` roi tra None.
        self._eligible = eligible or {}
        self._poll_raises = poll_raises
        self._transitions_raises = transitions_raises
        self.calls = []

    def poll_status(self, document_id):
        self.calls.append("poll_status")
        if self._poll_raises:
            raise self._poll_raises
        return self._state

    def available_transitions(self, instance_id, provider_user_id):
        self.calls.append("available_transitions")
        if self._transitions_raises:
            raise self._transitions_raises
        return self._transitions

    def eligible_recipients(self, instance_id, transition_id, provider_user_id):
        self.calls.append("eligible_recipients")
        v = self._eligible.get(str(transition_id), set())
        if isinstance(v, Exception):
            raise v
        if isinstance(v, tuple):
            self._last_eligible_error = v[1]
            return None
        return v

    # Duong GUI LENH. Ban gia van bay ra de neu endpoint lo cham vao thi test do ngay, thay
    # vi AttributeError mo ho.
    def approve_and_sign(self, *a, **kw):
        self.calls.append("approve_and_sign")
        raise AssertionError("endpoint chan doan vua GUI MOT LENH KY")

    def transition_with_recipients(self, *a, **kw):
        self.calls.append("transition_with_recipients")
        raise AssertionError("endpoint chan doan vua DOI TRANG THAI workflow")


DSR = {"name": "EC-DSR-2026-00027", "status": "Manual Review", "action": "Sign",
       "actor_type": "Approval Level", "actor_user": "phuong.nguyen1@ecentric.vn",
       "approver": "phuong.nguyen1@ecentric.vn", "package": "EC-DSP-2026-00028",
       "provider": "SCTS", "environment": "Production", "transition_id": -4,
       "request_attempt": 2,
       "effective_scts_user_id": "38445b30-5703-472f-8f92-832d77158d0f"}

DOC_ID = "d790d8e9-809d-44f9-9a24-c275600e7cc6"


class _D(dict):
    """Giong frappe._dict: doc duoc bang ca r["x"] lan r.x."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _saved_modules(*names):
    return {n: sys.modules.get(n) for n in names}


_PROVIDERS = "ecentric_workspace.platform.esign.providers"
_SAVED = {}
_ADAPTER_BOX = {"adapter": None}


def setUpModule():
    """Chi thay module `providers` (de tra ve adapter gia). `sanitize` dung ban THAT: thong
    diep loi phai la thong diep that thi phep kiem "co ghi ly do khong" moi co nghia."""
    _SAVED.update(_saved_modules(_PROVIDERS))
    stub = types.ModuleType(_PROVIDERS)
    stub.get_adapter = lambda settings: _ADAPTER_BOX["adapter"]
    sys.modules[_PROVIDERS] = stub
    # `package` phai thay bang ban gia: no `import frappe` o dau file, va tu 02/09
    # `provider_workflow_view` goi `workflow_instance_id` de biet nen hoi SCTS bang ma nao.
    # Ban gia tra None = "goi chua co ma instance", tuc nhanh lui ve document id - dung
    # trang thai cua moi goi hien co, nen day la mac dinh dung de kiem.
    _PKG = "ecentric_workspace.platform.esign.package"
    _SAVED.update(_saved_modules(_PKG))
    pkg_stub = types.ModuleType(_PKG)
    pkg_stub.workflow_instance_id = lambda pkg, fallback_to_document=True: None
    sys.modules[_PKG] = pkg_stub


def tearDownModule():
    for k, v in _SAVED.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


class _Perms(object):
    def __init__(self, raises=None):
        self.checked = 0
        self._raises = raises

    def assert_system_manager(self):
        self.checked += 1
        if self._raises:
            raise self._raises


def _load(dsr=None, doc_id=DOC_ID, settings=None, perms=None):
    """Nap ham THAT tu api.py bang exec(compile(...)).

    KHONG dung spec_from_file_location: loader do dung lai __pycache__, va mot dot bien chi
    DI CHUYEN khoi lenh se giu nguyen mtime+size -> cham ban cu -> xanh gia.
    """
    writes = []

    class _Db(object):
        @staticmethod
        def get_value(doctype, name=None, fields=None, **kw):
            if doctype == "EC Digital Signature Request":
                return _D(dsr) if dsr else None
            if doctype == "EC Digital Signature Package":
                return doc_id
            if doctype == "EC Digital Signature Provider Settings":
                return _D(settings) if settings else None
            raise AssertionError("truy van ngoai du kien: %s" % doctype)

        @staticmethod
        def set_value(*a, **kw):
            writes.append(("set_value", a))
            raise AssertionError("endpoint chi-doc vua GHI vao DB")

    fr = types.SimpleNamespace()
    fr.db = _Db
    fr.throw = lambda msg, *a, **kw: (_ for _ in ()).throw(_Boom(str(msg)))
    fr.log_error = lambda *a, **kw: None
    whitelist_kwargs = []

    def whitelist(**kw):
        whitelist_kwargs.append(kw)
        return lambda f: f

    fr.whitelist = whitelist
    env = {"frappe": fr, "_": lambda s: s, "perms": perms or _Perms()}
    exec(compile(_SRC, "api.py<%s>" % _FN_NAME, "exec"), env)
    env["_whitelist_kwargs"] = whitelist_kwargs
    env["_writes"] = writes
    return env


def _run(adapter, **kw):
    _ADAPTER_BOX["adapter"] = adapter
    env = _load(dsr=kw.pop("dsr", DSR), settings=kw.pop("settings", {"provider": "SCTS"}),
                doc_id=kw.pop("doc_id", DOC_ID), perms=kw.pop("perms", None))
    return env, env[_FN_NAME](**kw)


def _ok_adapter(**kw):
    kw.setdefault("state", _State("processing", [SIGNER_HOAN, SIGNER_PHUONG],
                                  identity={"doc_code": "PAYR-41"}))
    kw.setdefault("transitions", [APPROVE, REJECT])
    return _Adapter(**kw)


# --------------------------------------------------------------------------- chi System Manager
class TestOnlySystemManager(unittest.TestCase):
    def test_khong_phai_system_manager_thi_khong_hoi_duoc_gi(self):
        adapter = _ok_adapter()
        perms = _Perms(raises=_Boom("chi System Manager"))
        with self.assertRaises(_Boom, msg="bo cong quyen = ai dang nhap cung doc duoc trang "
                                          "thai ky cua hop dong nguoi khac"):
            _run(adapter, dsr_name="EC-DSR-2026-00027", perms=perms)
        self.assertEqual(adapter.calls, [],
                         "da chan quyen thi TUYET DOI khong duoc goi nha cung cap truoc do")

    def test_co_kiem_quyen_trong_moi_luot_chay(self):
        perms = _Perms()
        _run(_ok_adapter(), dsr_name="EC-DSR-2026-00027", perms=perms)
        self.assertEqual(perms.checked, 1, "khong goi assert_system_manager lan nao")


# --------------------------------------------------------------------------- chi doc
class TestReadOnly(unittest.TestCase):
    def test_la_GET_khong_phai_POST(self):
        node = _fn_node(_API, _FN_NAME)
        for dec in node.decorator_list:
            kws = [k.arg for k in getattr(dec, "keywords", [])]
            self.assertNotIn("methods", kws,
                             "chan doan ma POST-only thi khong go duoc tu thanh dia chi, va "
                             "no tu nhan minh la mot lenh ghi")

    def test_decorator_khong_khai_bao_methods_luc_chay(self):
        env = _load(dsr=DSR, settings={"provider": "SCTS"})
        self.assertEqual(env["_whitelist_kwargs"], [{}],
                         "phai la @frappe.whitelist() tran - mac dinh cho GET")

    def test_than_ham_khong_goi_bat_ky_duong_ghi_nao(self):
        forbidden = {"approve_and_sign", "transition_with_recipients", "set_dsr_status",
                     "set_value", "save", "insert", "delete_doc", "emit", "submit"}
        called = set()
        for n in ast.walk(_fn_node(_API, _FN_NAME)):
            if isinstance(n, ast.Call):
                f = n.func
                called.add(getattr(f, "attr", None) or getattr(f, "id", None))
        leak = called & forbidden
        self.assertEqual(leak, set(),
                         "goi duong ghi tu mot endpoint chan doan se tao chu ky THU HAI tren "
                         "chung tu da ky: %s" % sorted(leak))

    def test_khong_ghi_gi_khi_chay_that(self):
        env, out = _run(_ok_adapter(), dsr_name="EC-DSR-2026-00027")
        self.assertEqual(env["_writes"], [], "chay xong ma co ban ghi bi sua")
        self.assertTrue(out["ok"])

    def test_chi_goi_ba_ham_doc_cua_adapter(self):
        adapter = _ok_adapter()
        _run(adapter, dsr_name="EC-DSR-2026-00027")
        self.assertTrue(set(adapter.calls) <= _ALLOWED_ADAPTER_CALLS,
                        "goi them ham la cua nha cung cap: %s" % sorted(adapter.calls))


# --------------------------------------------------------------------------- khong lo du lieu
class TestNoPersonalDataLeaks(unittest.TestCase):
    def _out(self):
        _env, out = _run(_ok_adapter(), dsr_name="EC-DSR-2026-00027")
        return out

    def test_khong_co_ho_ten_cccd_dien_thoai_ngay_sinh(self):
        blob = json.dumps(self._out(), default=str, ensure_ascii=False)
        for secret in (NAME, "Tran Van Hoan", CCCD, MOBILE, DOB, "Cuc CS QLHC ve TTXH"):
            self.assertNotIn(secret, blob, "lo du lieu ca nhan: %s" % secret)

    def test_khoa_nhay_cam_khong_co_mat_trong_ket_qua(self):
        for row in self._out()["document"]["signers"]:
            for k in ("cccd", "mobile", "dob", "user", "identityPlace", "identityDate",
                      "display_name", "icon"):
                self.assertNotIn(k, row,
                                 "bo loc phai la loc TRANG: nha cung cap them truong thi no "
                                 "khong duoc tu chay ra ngoai (%s)" % k)

    def test_van_du_de_doi_soat(self):
        """Bit kin ma khong con doc duoc gi thi cong cu vo dung."""
        rows = self._out()["document"]["signers"]
        self.assertEqual([r["email"] for r in rows],
                         ["hoan.tran@ecentric.vn", "phuong.nguyen1@ecentric.vn"],
                         "email la khoa doi soat DUY NHAT con lai - payload khong co userId")
        self.assertEqual([r["status"] for r in rows], ["signed", "pending"],
                         "khong noi duoc ai da ky / chua ky thi khong tra loi duoc cau hoi")
        self.assertEqual(rows[1]["role"], "HOF", "o ky chua ai ky ma khong biet cua cap nao "
                                                 "thi no chi la '(chua gan)' vo danh")

    def test_payload_khong_co_userId_duoc_phoi_bay_chu_khong_bi_giau(self):
        rows = self._out()["document"]["signers"]
        self.assertIn("user_id", rows[0],
                      "cot user_id toan None chinh la bang chung rang doi soat phai dua vao "
                      "email - bo cot di thi lan sau lai co nguoi di tim signerId")
        self.assertIsNone(rows[0]["user_id"])


# --------------------------------------------------------------------------- tra loi ba cau hoi
class TestAnswersTheThreeQuestions(unittest.TestCase):
    def test_1_trang_thai_tai_lieu(self):
        _env, out = _run(_ok_adapter(), dsr_name="EC-DSR-2026-00027")
        self.assertEqual(out["document"]["status"], "processing")
        self.assertTrue(out["document"]["ok"])
        self.assertEqual(out["document"]["signer_count"], 2)

    def test_2_cac_canh_chuyen_kha_dung(self):
        _env, out = _run(_ok_adapter(), dsr_name="EC-DSR-2026-00027")
        self.assertEqual(out["transitions"]["count"], 2)
        self.assertEqual([t["transition_id"] for t in out["transitions"]["items"]],
                         ["-4", "-7"])
        self.assertEqual(out["transitions"]["items"][0]["transition_name"], "Phê duyệt")

    def test_3_ai_duoc_nhan_buoc_nay(self):
        other = "aaaa1111-2222-4333-8444-555555555555"
        adapter = _ok_adapter(eligible={"-4": {other}, "-7": {DSR["effective_scts_user_id"]}})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        by_tid = {r["transition_id"]: r for r in out["recipients"]}
        self.assertFalse(by_tid["-4"]["includes_provider_user"],
                         "day chinh la cau tra loi cua su co: eContract nhan 2xx roi khong "
                         "lam gi vi nguoi nay khong duoc nhan buoc do")
        self.assertTrue(by_tid["-7"]["includes_provider_user"])
        self.assertEqual(by_tid["-4"]["count"], 1)

    def test_hoi_dung_mot_canh_khi_duoc_chi_dinh(self):
        adapter = _ok_adapter(eligible={"-4": {DSR["effective_scts_user_id"]}})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027", transition_id="-4")
        self.assertEqual([r["transition_id"] for r in out["recipients"]], ["-4"])

    def test_hoi_ho_ve_MOT_NGUOI_KHAC_duoc(self):
        adapter = _ok_adapter(eligible={"-4": set(), "-7": set()})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027",
                         provider_user_id="cccc3333-4444-4555-8666-777777777777")
        self.assertEqual(out["provider_user_id"], "cccc3333-4444-4555-8666-777777777777",
                         "doi soat mot nguoi khac la mot CAU HOI, khong phai mot hanh dong")

    def test_khong_ban_pha_nha_cung_cap(self):
        many = [dict(APPROVE, transition_id=str(-i)) for i in range(30)]
        adapter = _ok_adapter(transitions=many)
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        self.assertLessEqual(len(out["recipients"]), 10,
                             "mot lan chan doan khong duoc bien thanh mot tran request")


# --------------------------------------------------------------------------- khong nuot loi
class TestFailuresAreExplainedNotSwallowed(unittest.TestCase):
    def test_doc_tai_lieu_that_bai_thi_NOI_RA(self):
        adapter = _ok_adapter(poll_raises=_Boom("SCTS 503 tam thoi"))
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        d = out["document"]
        self.assertFalse(d["ok"])
        self.assertIn("SCTS 503", d["error"] or "",
                      "khoi rong khong kem ly do se bi doc thanh 'tai lieu khong co nguoi "
                      "ky nao' - dung ket luan sai da tung dong mot cap duyet")
        self.assertTrue(d["asked"])

    def test_hoi_canh_chuyen_that_bai_thi_NOI_RA(self):
        adapter = _ok_adapter(transitions_raises=_Boom("HTTP 400 duong chuyen"))
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        self.assertFalse(out["transitions"]["ok"])
        self.assertIn("400", out["transitions"]["error"] or "")
        self.assertIsNone(out["transitions"]["count"],
                          "count=0 khi KHONG HOI DUOC la mot lo'i noi doi: no doc ra thanh "
                          "'nguoi nay khong con buoc nao de di'")

    def test_khong_hoi_duoc_nguoi_nhan_thi_kem_ly_do(self):
        adapter = _ok_adapter(eligible={"-4": ("none", "Timeout: users-for-transition"),
                                        "-7": set()})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        row = {r["transition_id"]: r for r in out["recipients"]}["-4"]
        self.assertFalse(row["ok"])
        self.assertIn("users-for-transition", row["error"] or "",
                      "lop bao ve tung im lang y het the nay va khong ai biet vi sao no "
                      "khong chay")
        self.assertIsNone(row["includes_provider_user"],
                          "khong hoi duoc thi khong duoc ket luan 'khong nam trong danh sach'")

    def test_ngoai_le_khi_hoi_nguoi_nhan_cung_kem_ly_do(self):
        adapter = _ok_adapter(eligible={"-4": _Boom("connection reset"), "-7": set()})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        row = {r["transition_id"]: r for r in out["recipients"]}["-4"]
        self.assertFalse(row["ok"])
        self.assertIn("connection reset", row["error"] or "")

    def test_HOI_DUOC_MA_RONG_khac_han_KHONG_HOI_DUOC(self):
        adapter = _ok_adapter(eligible={"-4": set(), "-7": ("none", "HTTP 500")})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        by_tid = {r["transition_id"]: r for r in out["recipients"]}
        self.assertTrue(by_tid["-4"]["ok"], "hoi duoc va danh sach rong VAN la mot cau tra loi")
        self.assertEqual(by_tid["-4"]["count"], 0)
        self.assertIsNone(by_tid["-4"]["error"])
        self.assertFalse(by_tid["-4"]["includes_provider_user"])
        self.assertFalse(by_tid["-7"]["ok"], "hai cai nay dan toi hai quyet dinh khac han")

    def test_ly_do_that_bai_khong_duoc_dinh_nham_sang_canh_khac(self):
        """`_last_eligible_error` chi duoc GHI luc that bai va khong bao gio duoc xoa."""
        adapter = _ok_adapter(eligible={"-4": ("none", "HTTP 500 canh -4"), "-7": None})
        _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027")
        row = {r["transition_id"]: r for r in out["recipients"]}["-7"]
        self.assertNotIn("canh -4", row["error"] or "",
                         "gan ly do cua canh truoc cho canh sau = mot cau tra loi sai ma "
                         "nguoi doc tin tuong hoan toan")
        self.assertTrue(row["error"], "van phai noi mot cai gi do, khong duoc de trong")

    def test_thieu_du_lieu_thi_noi_ro_thieu_cai_gi(self):
        for kw, reason in ((dict(doc_id=None), "no_provider_document"),
                           (dict(dsr=dict(DSR, effective_scts_user_id=None)),
                            "no_provider_user_id"),
                           (dict(settings=None), "no_provider_settings")):
            adapter = _ok_adapter()
            _env, out = _run(adapter, dsr_name="EC-DSR-2026-00027", **kw)
            self.assertFalse(out["ok"])
            self.assertEqual(out["reason"], reason)
            self.assertEqual(adapter.calls, [], "chua du dieu kien thi dung goi nha cung cap")

    def test_khong_tim_thay_chan_ky_thi_nem_loi(self):
        with self.assertRaises(_Boom, msg="tra ve rong se bi doc thanh 'chan ky nay khong "
                                          "co viec gi'"):
            _run(_ok_adapter(), dsr_name="KHONG-CO", dsr=None)


if __name__ == "__main__":
    unittest.main()
