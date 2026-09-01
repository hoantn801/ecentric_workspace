# Copyright (c) 2026, eCentric and contributors
"""Contract Review — logic thuần chạy độc lập, không cần bench:
    python3 ecentric_workspace/approval_center/tests/test_contract_review_service.py
Khoá 3 quyết định nghiệp vụ Hoàn chốt 2026-09-01:
  (a) hợp đồng SẴN CÓ chỉ điều chỉnh (tiền/thời hạn/chi tiết) -> bỏ cấp CEO;
      đổi NỘI DUNG (loại HĐ, brand, mục đích...) -> đủ 4 cấp;
  (b) deadline theo NGÀY LÀM VIỆC: sẵn có 1 ngày, mới 3 ngày (bỏ T7/CN);
  (c) engine.submit chỉ được bỏ cấp KHÔNG mandatory, có ghi audit.
"""
import os
import sys
import types
from datetime import datetime


def _fake_frappe():
    fake = types.ModuleType("frappe")
    fake.whitelist = lambda *a, **k: (lambda f: f)
    fake._ = lambda s: s
    fake.session = types.SimpleNamespace(user="test@ecentric.vn")
    fake.get_roles = lambda u=None: []
    fake.db = types.SimpleNamespace(get_value=lambda *a, **k: None, set_value=lambda *a, **k: None)
    fake.utils = types.ModuleType("frappe.utils")
    fake.utils.now_datetime = lambda: datetime(2026, 9, 1, 10, 0)   # thứ Ba
    fake.log_error = lambda *a, **k: None
    def throw(msg, *a, **k):
        raise Exception(msg)
    fake.throw = throw
    sys.modules["frappe"] = fake
    sys.modules["frappe.utils"] = fake.utils
    return fake


def _load_service():
    _fake_frappe()
    # engine giả để import module service mà không kéo cả transitions
    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.submit = lambda *a, **k: "EC-APR-TEST"
    eng.resubmit = lambda *a, **k: None
    eng.notify = lambda *a, **k: None
    eng.resolve_process = lambda *a, **k: None
    eng.resolve_levels = lambda *a, **k: []
    eng.resolve_participants = lambda *a, **k: []
    wf = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    wf.transitions = eng
    sys.modules["ecentric_workspace.approval_center.shared.workflow"] = wf
    sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = eng
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
    import importlib
    return importlib.import_module(
        "ecentric_workspace.approval_center.features.contract_review.application.service")


class _Doc(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)
    __getattr__ = lambda self, k: self.get(k)


def main():
    svc = _load_service()
    fails = []

    def chk(name, cond):
        print(("PASS" if cond else "FAIL") + " - " + name)
        if not cond:
            fails.append(name)

    prev = {"contract_type": "Sales / Bán ra (EC)", "request_type": "Template from EC / Mẫu theo khung EC",
            "brand": "FES-VN", "justification": "Booking KOL", "contract_value": 100,
            "contract_start_date": "2026-01-01", "contract_end_date": "2026-06-30",
            "request_details": "Điều khoản cũ"}

    # (a) chỉ đổi số tiền + thời hạn -> bỏ CEO
    doc = _Doc(prev, request_kind="Existing", previous_request="EC-CTR-1",
               contract_value=200, contract_end_date="2026-12-31")
    ch = svc.changed_vs_previous(doc, prev)
    chk("diff bat dung truong doi", sorted(ch) == ["contract_end_date", "contract_value"])
    chk("chi dieu chinh -> bo cap CEO", svc.skip_ceo(doc, ch) is True)

    # đổi cả brand -> nội dung đổi -> đủ 4 cấp
    doc2 = _Doc(prev, request_kind="Existing", previous_request="EC-CTR-1", brand="ANDROS-VN")
    ch2 = svc.changed_vs_previous(doc2, prev)
    chk("doi brand -> du 4 cap", svc.skip_ceo(doc2, ch2) is False)

    # hợp đồng mới -> không bao giờ bỏ cấp
    doc3 = _Doc(prev, request_kind="New", previous_request="")
    chk("hop dong moi -> du 4 cap", svc.skip_ceo(doc3, []) is False)
    # Existing nhưng quên chọn gốc -> không bỏ cấp (an toàn)
    doc4 = _Doc(prev, request_kind="Existing", previous_request="")
    chk("existing khong co goc -> khong bo cap", svc.skip_ceo(doc4, []) is False)

    # (b) deadline ngày làm việc — 2026-09-01 là thứ Ba
    d1 = svc.business_deadline("Existing", datetime(2026, 9, 1, 10, 0))
    chk("san co: +1 ngay lam viec (Ba->Tu)", str(d1) == "2026-09-02")
    d3 = svc.business_deadline("New", datetime(2026, 9, 1, 10, 0))
    chk("moi: +3 ngay lam viec (Ba->Sau)", str(d3) == "2026-09-04")
    d_fri = svc.business_deadline("Existing", datetime(2026, 9, 4, 15, 0))  # thứ Sáu
    chk("gui thu Sau: +1 ngay lam viec = thu Hai", str(d_fri) == "2026-09-07")
    d_fri3 = svc.business_deadline("New", datetime(2026, 9, 4, 15, 0))
    chk("gui thu Sau: +3 ngay lam viec = thu Tu", str(d_fri3) == "2026-09-09")

    # đồng bộ danh sách với UI: ADJUST_ONLY của form phải khớp service
    ui = open(os.path.join(os.path.dirname(__file__), "..", "features", "contract_review",
                           "ui", "main_section.html"), encoding="utf-8").read()
    import re as _re
    m = _re.search(r'var ADJUST_ONLY=\[([^\]]+)\]', ui)
    ui_fields = set(x.strip().strip('"') for x in m.group(1).split(",")) if m else set()
    chk("ADJUST_ONLY cua UI khop server", ui_fields == set(svc.ADJUST_ONLY_FIELDS))
    m2 = _re.search(r'var DIFF_FIELDS=\[([^\]]+)\]', ui)
    ui_diff = [x.strip().strip('"') for x in m2.group(1).split(",")] if m2 else []
    chk("DIFF_FIELDS cua UI khop server", ui_diff == list(svc.DIFF_FIELDS))

    # (d) BUG-3/BUG-4 từ E2E prod 01/09 — hai chốt server-side phải TỒN TẠI và ĐÚNG CHỖ
    src = open(os.path.join(os.path.dirname(__file__), "..", "features", "contract_review",
                            "application", "service.py"), encoding="utf-8").read()
    chk("BUG-4: submit doi hop dong goc DA DUYET (server-side)",
        "_require_approved_previous(doc.previous_request)" in src
        and '"Approved"' in src.split("def _require_approved_previous")[1].split("def ")[0])
    chk("BUG-3: resubmit co guard chan lach CEO",
        "_guard_resubmit_needs_ceo(doc)" in src.split("def resubmit")[1].split("def _guard")[0])
    guard = src.split("def _guard_resubmit_needs_ceo")[1]
    chk("BUG-3: guard xet snapshot co cap CEO khong",
        "EC Approval Request Level" in guard and "CEO_LEVEL_NO" in guard)
    chk("BUG-3: chieu nguoc (het can CEO) van cho qua", "if not needs_ceo:" in guard and "return" in guard)

    # (c) engine: skip chỉ với cấp không mandatory + có audit
    eng_src = open(os.path.join(os.path.dirname(__file__), "..", "shared", "workflow",
                                "transitions.py"), encoding="utf-8").read()
    chk("engine chan bo cap mandatory", "is mandatory and cannot be skipped" in eng_src)
    chk("engine ghi audit khi bo cap", '"Skipped", requester' in eng_src)
    chk("engine giu mac dinh (khong skip thi nguyen hanh vi)",
        "skip_level_nos=None" in eng_src)

    print("SOME_FAIL" if fails else "ALL_PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
