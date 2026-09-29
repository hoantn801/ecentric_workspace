"""F15 (29/09/2026): ham @frappe.whitelist trong approval_center KHONG duoc nhan `actor` / `user`.

Truoc 29/09 co 39 ham o `features/*/application/` vua whitelist vua nhan nguoi thao tac lam
tham so: goi thang /api/method/...application.service.<ham> kem `actor=`/`user=` tuy y la mao
danh duoc - duyet thay cap hien tai cua AI top-up (`finance_approve(actor=...)`), hoan tat
viec cua nguoi khac bang `user="Administrator"` (get_roles tra System Manager), resubmit ho
phieu Information Required. Cua HTTP duy nhat la `controllers/api.py` (bind / bind_fulfillment),
lay nguoi thao tac tu `frappe.session.user`; tham so actor/user chi de goi noi bo va test.

Quet ma (AST), khong chay frappe:
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_no_whitelisted_actor_param.py
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]          # approval_center/
CAM = {"actor", "user"}


def _vi_pham():
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        if "tests" in p.parts:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any("whitelist" in ast.unparse(d) for d in n.decorator_list):
                continue
            args = {a.arg for a in n.args.args + n.args.kwonlyargs}
            if args & CAM:
                out.append("%s:%s(%s)" % (p.relative_to(ROOT), n.name, ", ".join(sorted(args & CAM))))
    return out


def test_khong_ham_whitelist_nao_nhan_nguoi_thao_tac():
    assert _vi_pham() == []


def test_con_quet_thay_ham_whitelist():
    # Chan mu: neu cach quet hong (khong thay ham whitelist nao) thi test tren xanh vo nghia.
    n = 0
    for p in ROOT.rglob("*.py"):
        if "tests" in p.parts:
            continue
        n += p.read_text(encoding="utf-8").count("@frappe.whitelist")
    assert n > 50


def test_cac_ham_da_go_van_con_va_goi_noi_bo_duoc():
    # Go decorator, KHONG go ham: bind()/facade van goi service.resubmit / claim / complete.
    import re
    src = (ROOT / "features" / "ai_topup" / "application" / "service.py").read_text(encoding="utf-8")
    for fn in ("resubmit", "finance_approve", "claim_fulfillment", "complete_fulfillment"):
        assert re.search(r"^def %s\(" % fn, src, re.M), fn
