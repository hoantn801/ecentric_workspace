"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.definition_support import (
    BrandAndDepartmentOptions, ExactAndDateFilters, ServiceMethod, service_callbacks,
)

from ecentric_workspace.approval_center.features.contract_review.domain import esign_flow as _esign_flow

_KOL = "ecentric_workspace.approval_center.features.contract_review.application.kol_service"

CONTRACT_REVIEW_DEFINITION = ApprovalDefinition(
    code="CONTRACT_REVIEW", business_doctype="EC Contract Review Request", feature="contract_review",
    editable_fields=("request_title", "request_kind", "previous_request", "contract_type",
                     "request_type", "brand", "justification", "contract_value",
                     "contract_start_date", "contract_end_date", "request_details",
                     "cc_to", "request_attachment", "department", "company",
                     # Hop dong KOL/KOC (11/11/2026). So tien tinh san (gross/thue/so tra), so
                     # HD, tep sinh ra, trang thai ky KHONG nam day: chi server ghi.
                     # `sales_order` bo 12/11: SO doanh thu chon o DNTT (phieu cu giu gia tri).
                     "creator", "service_type", "platform", "quantity",
                     "duration", "air_dates", "commission_rate", "amount_type", "amount_input",
                     "pit_rate", "vat_rate", "payment_schedule", "advance_percent",
                     "payment_term_days", "contract_template", "contract_date",
                     # Quy trinh ky tren cong (12/11, chot voi chat Ky so) - xem domain/esign_flow.py.
                     "esign_flow", "partner_signer_name", "partner_signer_email", "partner_signer_phone"),
    my_request_fields=("name", "request_title", "request_kind", "contract_type", "brand",
                       "contract_value", "expected_response_date", "approval_request",
                       "creation", "modified"),
    approval_list_fields=("name", "request_title", "request_kind", "contract_type", "brand",
                          "contract_value", "expected_response_date", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=BrandAndDepartmentOptions((
        ("request_kinds", ("Existing", "New")),
        ("contract_types", ("Purchase / Mua vào (EC)", "Sales / Bán ra (EC)",
                            "Service / Dịch vụ (GBSxBrand)", "KOL/KOC / Creator (EC)",
                            "Labor / Hợp đồng lao động (EC)")),
        # [ma, nhan] - luu ma, hien nhan.
        ("esign_flows", tuple((k, v) for k, v in _esign_flow.LABELS.items())),
        ("esign_flows_with_partner", _esign_flow.WITH_PARTNER),
        # "loai HD|quy trinh mac dinh" - trang chi HIEN goi y, server dien that (esign_flow.apply_default).
        ("esign_flow_defaults", tuple("%s|%s" % kv for kv in _esign_flow.DEFAULTS.items())),
        ("kol_service_types", ("Livestream", "Video", "Livestream + Video", "Hoa hồng affiliate")),
        ("kol_platforms", ("TikTok", "Shopee", "Facebook", "Khác")),
        ("kol_payment_schedules", ("Thanh toán sau nghiệm thu", "Cọc trước")),
        ("kol_advance_percents", ("20", "30", "40", "50")),
        ("request_types", ("Template from EC / Mẫu theo khung EC",
                           "Template from partner / Mẫu theo khung đối tác",
                           "New contract template / Hợp đồng mới")),
    )),
    filter_builder=ExactAndDateFilters(("contract_type", "request_kind")),
    # Ngay ky cua phieu goc la ngay tu tinh theo lich CU: chep sang phieu moi thi bi coi la ngay
    # nguoi dung chon va "dinh" lai (QC 12/11). De trong - server tinh lai theo lich cua phieu moi.
    clone_exclude_fields=("contract_date",),
    draft_preparer=ServiceMethod(_KOL, "prepare_draft"),
    detail_extender=ServiceMethod(_KOL, "detail_extra"),
    **service_callbacks("contract_review"))


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
CONTRACT_REVIEW_DEFINITION = _dc_replace(
    CONTRACT_REVIEW_DEFINITION,
    quick_summary=(
        ("Loại hợp đồng", "contract_type"),
        ("Brand", "brand"),
        ("Giá trị", "contract_value"),
        ("Hiệu lực từ", "contract_start_date"),
    ),
)


# Tab "Tat ca" (16/10/2026, Finance gop y, PO duyet): them cot + o loc theo truong nghiep vu.
# "Gia tri" trung truong so tien cua form (business_summary.AMOUNT_FIELDS) nen KHONG thanh
# cot moi - no doi nhan cot "So tien" san co thanh "Gia tri". Xem all_list.py.
CONTRACT_REVIEW_DEFINITION = _dc_replace(
    CONTRACT_REVIEW_DEFINITION,
    all_tab_columns=(
        ("Legal entity / Brand", "brand", "text"),
        ("Loại hợp đồng", "contract_type", "select"),
        ("Giá trị", "contract_value", "money"),
    ),
    all_tab_filters=("brand", "contract_type"),
)
