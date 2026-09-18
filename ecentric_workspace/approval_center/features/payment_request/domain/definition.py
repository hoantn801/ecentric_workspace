"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.finance_support import Resubmitter, Submitter
from ecentric_workspace.approval_center.features.payment_request.application.service import (
    detail_extra, normalize_payment, payment_title, validate_payment)
from ecentric_workspace.approval_center.shared.definition_support import (
    DepartmentOptions, ExactAndDateFilters, ExpenseCategoryOptions, StaticOptions)


def _make(code, doctype, editable, mine, approvals, options, title, validator,
          manager=False, esign=False, draft_preparer=None, detail_extender=None,
          ai_exclude=(), ai_hints=None):
    return ApprovalDefinition(
        # `feature` la duong dan module ma fulfillment_service.claim/complete import
        # (features.<feature>.application.service). Thieu no thi buoc 6 "Finance xu ly UNC"
        # khong goi duoc (07/09).
        code=code, business_doctype=doctype, feature="payment_request", editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        title_builder=title, filter_builder=ExactAndDateFilters(),
        submitter=Submitter(doctype, code, validator, title, manager, esign),
        resubmitter=Resubmitter(doctype, title), draft_preparer=draft_preparer,
        detail_extender=detail_extender,
        # O tich "Toi xac nhan thong tin va tep dinh kem la chinh xac" la mot CAM KET CA
        # NHAN. Chep no sang phieu moi la ky thay nguoi dung cho mot bo ho so ho chua doc
        # lai - nguoi de nghi phai tu tich lai.
        clone_exclude_fields=("details_and_attachments_correct",),
        ai_exclude_fields=ai_exclude,
        ai_hints=ai_hints or {})

PAYMENT_REQUEST_DEFINITION = _make(
    "PAYMENT_REQUEST", "EC Payment Request",
    ("request_title", "reason", "payment_amount", "payment_date", "payee_full_name",
     "account_bank", "bank_account_number", "has_purchase_request", "purchase_request",
     "funding_source_doctype", "funding_source_name",
     "no_purchase_request_reason", "is_cost_valid", "details_and_attachments_correct",
     "request_attachment", "department", "company",
     # chia dot (07/09): installment_no / installment_of do SERVER dat, KHONG cho client sua
     "payment_mode", "total_amount", "next_installment_amount", "next_installment_date",
     # phan loai chi phi (09/09, Hoan) - PnL doc de gom nhom va chong dem trung luong.
     # `ec_can_brand` KHONG nam day: no fetch tu danh muc, client sua duoc thi lop an/hien
     # brand tu no lai thanh khai bao tu do.
     "ec_loai_chi_phi", "ec_brand",
     # 12/09, Hoan: brand ngoai danh muc (theo dung khuon Booking Request), ky ghi nhan chi
     # phi = thang HOAT DONG, va thue suat VAT nam trong so tien. Thieu o day thi form gui
     # len bao nhieu cung bi bo im lang - client sua duoc dung nhung gi liet ke trong nay.
     "ec_brand_moi", "ec_brand_ten", "ec_ky_chi_phi", "ec_vat_pct"),
    ("name", "request_title", "payee_full_name", "payment_amount", "payment_date",
     "approval_request", "fulfillment_status", "payment_mode", "installment_no", "installment_of",
     "creation", "modified"),
    ("name", "request_title", "payee_full_name", "payment_amount", "payment_date", "creation"),
    ExpenseCategoryOptions((("yes_no", ("Yes", "No")),)), payment_title, validate_payment,
    manager=True, esign=True, draft_preparer=normalize_payment,
    # Truong nguoi lap PHAI tu lam, du chung nam trong `editable_fields`. Xem
    # `ApprovalDefinition.ai_exclude_fields`. `details_and_attachments_correct` KHONG can ke
    # o day: no da nam trong `clone_exclude_fields` va bi chan boi luat so 2.
    #
    # TIEU DE: form da TU SINH mot tieu de tu te ("Bo trong se tu sinh: Payment Request -
    # Nguoi nhan - So tien"), nen AI chep nguyen ten hop dong vao day la LAM TE HON - mat
    # ca nguoi nhan lan so tien. Bao no ghep ca ba; khong co ten hop dong thi de trong cho
    # form tu sinh. Mot cau chi dan cho MOT truong, khong phai schema viet tay cho form.
    ai_hints={
        "request_title":
            "Dat theo mau: <ten hop dong hoac chung tu> - <nguoi nhan> - <so tien>. "
            "Van ban KHONG neu ten hop dong/chung tu thi DE TRONG, he thong tu sinh tieu de. "
            "Khong chep nguyen tieu de dai cua hop dong vao day.",
    },
    ai_exclude=(
        # "Chi phi hop le?" la phan doan cua nguoi de nghi, khong phai du kien tren hop dong.
        "is_cost_valid",
        # Chon "Yes" la keo theo chung tu nguon; AI khong chon duoc nguon (co phan quyen,
        # chi hien chung tu DA DUYET cua chinh nguoi do) nen phieu se khong gui duoc.
        "has_purchase_request", "funding_source_doctype", "funding_source_name",
        "purchase_request",
        # Gui di la TAO mot ban ghi Brand moi (chot_brand_ngoai). Khong de AI dat ten danh muc.
        "ec_brand_ten",
        # Chia dot la quyet dinh ve dong tien, khong doc ra tu ho so.
        "payment_mode", "total_amount", "next_installment_amount", "next_installment_date",
        # Server tu dat tu ho so nhan su trong save_draft.
        "department", "company",
    ),
    # `detail_extra` = installments_block + unc_fix_block. Truoc day tro THANG vao
    # `installments_block`; doi sang ham gop de them khoi "thay file UNC" ma khong phai nhet
    # mot khai niem rieng cua phieu thanh toan vao `capabilities.derive` dung chung 8 form.
    detail_extender=detail_extra)


