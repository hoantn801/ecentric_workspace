# Copyright (c) 2026, eCentric and contributors
"""get_previous_contract KHÔNG được rò dữ liệu hợp đồng. Chạy độc lập:
    python3 ecentric_workspace/approval_center/tests/test_contract_review_read_permission.py

Bối cảnh (03/09): hàm này đọc bằng frappe.db.get_value — bỏ qua permission. Mã hồ sơ chạy
tuần tự nên mọi nhân viên đăng nhập đều dò được giá trị + điều khoản hợp đồng của mọi phòng.
Test kiểm HÀNH VI: không có quyền thì phải NÉM LỖI và KHÔNG trả về dữ liệu — không kiểm
kiểu "có gọi can_view_request hay không" (kiểu đó stub tự trả lời chính nó, vô dụng).
"""
import importlib
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

ROW = {"name": "EC-CTR-2026-00003", "request_title": "HĐ mật", "contract_type": "Purchase",
       "request_type": "Template", "brand": "FES-VN", "justification": "Booking",
       "contract_value": 999000000, "contract_start_date": "2026-01-01",
       "contract_end_date": "2026-12-31", "request_details": "Điều khoản mật",
       "requested_by": "nguoi.khac@ecentric.vn", "approval_request": "EC-APR-2026-00003"}


class Boom(Exception):
    pass


def _load(can_view_result):
    for mod in [m for m in list(sys.modules) if m.startswith(("frappe", "ecentric_workspace"))]:
        sys.modules.pop(mod, None)
    fake = types.ModuleType("frappe")
    fake.whitelist = lambda *a, **k: (lambda f: f)
    fake._ = lambda s: s
    fake.PermissionError = Boom
    fake.session = types.SimpleNamespace(user="ke.to.mo@ecentric.vn")
    fake.get_roles = lambda u=None: []
    fake.db = types.SimpleNamespace(get_value=lambda *a, **k: dict(ROW))
    fake.get_all = lambda *a, **k: []

    def throw(msg, exc=None):
        raise (exc or Boom)(msg)
    fake.throw = throw
    sys.modules["frappe"] = fake

    adapter = types.ModuleType("ecentric_workspace.approval_center.shared.api_adapter")
    adapter.bind = lambda code: {}
    sys.modules["ecentric_workspace.approval_center.shared.api_adapter"] = adapter
    perms = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
    perms.can_view_request = lambda *a, **k: can_view_result
    sys.modules["ecentric_workspace.approval_center.shared.workflow.permissions"] = perms

    sys.path.insert(0, ROOT)
    return importlib.import_module(
        "ecentric_workspace.approval_center.features.contract_review.controllers.api")


fails = []


def chk(name, cond):
    print(("PASS" if cond else "FAIL") + " - " + name)
    if not cond:
        fails.append(name)


# 1) KHÔNG có quyền -> phải ném lỗi, tuyệt đối không trả dữ liệu
api = _load(can_view_result=False)
leaked = None
try:
    leaked = api.get_previous_contract("EC-CTR-2026-00003")
    blocked = False
except Boom:
    blocked = True
chk("khong co quyen -> NEM LOI", blocked)
chk("khong co quyen -> KHONG tra du lieu", leaked is None)

# 2) CÓ quyền -> trả dữ liệu, nhưng không kèm trường nội bộ
api = _load(can_view_result=True)
row = api.get_previous_contract("EC-CTR-2026-00003")
chk("co quyen -> tra du lieu de tu dien", row and row.get("contract_value") == 999000000)
chk("khong ro ri truong noi bo (requested_by / approval_request)",
    "requested_by" not in row and "approval_request" not in row)

# 3) đúng doctype + mã loại được truyền vào chốt quyền (sai thì chốt xét nhầm hồ sơ)
src = open(os.path.join(ROOT, "ecentric_workspace", "approval_center", "features",
                        "contract_review", "controllers", "api.py"), encoding="utf-8").read()
call = src.split("can_view_request(")[1].split("):")[0]
chk("truyen approval_request lam dinh danh phieu", "row.get(\"approval_request\")" in call)
chk("truyen dung business_doctype + approval_type", "_DT" in call and "_CODE" in call)

print("SOME_FAIL" if fails else "ALL_PASS")
sys.exit(1 if fails else 0)
