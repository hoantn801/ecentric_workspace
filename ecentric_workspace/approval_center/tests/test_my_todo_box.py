# Copyright (c) 2026, eCentric and contributors
"""Tab 'Chờ tôi xử lý' phải gồm CẢ hồ sơ đang chờ chính mình duyệt.

Chạy độc lập, không cần bench:
    python3 ecentric_workspace/approval_center/tests/test_my_todo_box.py

Bối cảnh: EC-APR-2026-00085 đang ở 'Operation Review / Chờ duyệt' và chờ Hoàn bấm duyệt,
nhưng tab 'Chờ tôi xử lý' không hiện — vì tab đó chỉ lọc phần fulfilment sau khi duyệt xong.
"""
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _install_fake_frappe():
    """Nạp queries.py mà không cần bench: chỉ cần các thuộc tính module dùng lúc import."""
    fake = types.ModuleType("frappe")
    fake.db = types.SimpleNamespace(sql=lambda *a, **k: [])
    fake.get_all = lambda *a, **k: []
    fake.get_meta = lambda *a, **k: None
    fake.session = types.SimpleNamespace(user="test@ecentric.vn")
    sys.modules.setdefault("frappe", fake)
    return fake


def _load_queries():
    _install_fake_frappe()
    sys.path.insert(0, ROOT)
    scope_mod = types.ModuleType("ecentric_workspace.approval_center.reporting.scope")
    scope_mod.scope_predicate = lambda scope: ("1=1", {})
    sys.modules["ecentric_workspace.approval_center.reporting.scope"] = scope_mod
    import importlib
    return importlib.import_module("ecentric_workspace.approval_center.reporting.queries")


def main():
    q = _load_queries()
    fails = []

    def chk(name, cond):
        print(("PASS" if cond else "FAIL") + " - " + name)
        if not cond:
            fails.append(name)

    sql = q.awaiting_my_decision_sql("_me_todo")
    chk("chi tinh dong approver o DUNG cap hien tai",
        "va.level_no = r.current_level" in sql)
    chk("chi tinh dong con Pending (chua quyet dinh)",
        "va.status = 'Pending'" in sql)
    chk("chi tinh ho so con mo",
        "r.approval_status IN ('Pending','Information Required')" in sql)
    chk("dung tham so hoa, khong noi chuoi gia tri",
        "%(_me_todo)s" in sql and "test@ecentric.vn" not in sql)

    # Không có việc fulfilment nào -> tab vẫn phải hiện hồ sơ chờ tôi duyệt
    q._fulfillment_refs = lambda me=None: []
    params = {}
    clause = q._my_todo_clause("hoan.tran@ecentric.vn", params)
    chk("khong co viec fulfilment van hien ho so cho toi duyet",
        "va.status = 'Pending'" in clause and clause != "1=0")
    chk("dua email vao params chu khong vao cau SQL",
        params.get("_me_todo") == "hoan.tran@ecentric.vn")

    # Có cả hai -> phải là phép HỢP (OR), không phải giao
    q._fulfillment_refs = lambda me=None: ["EC-SYSREQ-1", "EC-SYSREQ-2"]
    params = {}
    clause = q._my_todo_clause("hoan.tran@ecentric.vn", params)
    chk("gop hai ve bang OR", " OR " in clause)
    chk("co ve fulfilment", "r.reference_name IN (%(_ff0)s, %(_ff1)s)" in clause)
    chk("co ve cho toi duyet", "va.level_no = r.current_level" in clause)
    chk("tham so hoa ca danh sach fulfilment",
        params.get("_ff0") == "EC-SYSREQ-1" and params.get("_ff1") == "EC-SYSREQ-2")

    # Không đăng nhập / không có việc gì -> không được lọt hồ sơ nào
    q._fulfillment_refs = lambda me=None: []
    chk("khong co gi thi khong lot ho so nao", q._my_todo_clause(None, {}) == "1=0")

    # Tab khác không được đổi hành vi
    params = {}
    w = q._list_where({}, {"box": "received", "_me": "hoan.tran@ecentric.vn"}, None, params)
    chk("tab 'Da nhan' van la approver bat ky (khong doi)",
        "va.approver = %(_me_recv)s" in w and "va.status = 'Pending'" not in w)

    print("SOME_FAIL" if fails else "ALL_PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
