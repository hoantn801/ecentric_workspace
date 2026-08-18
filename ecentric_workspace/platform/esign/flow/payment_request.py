# Copyright (c) 2026, eCentric and contributors
"""THE single, hard-coded esign flow: EC Payment Request / PAYMENT_REQUEST.

Phase 1 (2026-08-18): declarative only. Nothing in ``esign`` reads this yet - guard.py,
requester.py, tasks.py, orchestrator.py, ui_state.py, inbox.py keep deciding everything
they decide today. This module exists so the sequence can be read in one place instead of
traced across 8 files, and so ``drift.check()`` can flag when the live
`EC Digital Signature Profile` policy fields stop matching what this flow assumes.

There is deliberately ONE flow declared here, for ONE (business_doctype, approval_type)
pair. Do not generalize this into a variant registry before a second consumer exists -
see the platform/esign discussion this module grew out of. When a second signing flow is
needed, that is the trigger to add a lookup keyed by (business_doctype, approval_type),
not before.
"""
from ecentric_workspace.platform.esign.flow.steps import step

BUSINESS_DOCTYPE = "EC Payment Request"
APPROVAL_TYPE = "PAYMENT_REQUEST"

# ---------------------------------------------------------------------------------
# Expected EC Digital Signature Profile policy for this flow. drift.check() compares
# these against the live, single enabled Profile row for (BUSINESS_DOCTYPE,
# APPROVAL_TYPE) and reports mismatches - it never writes, and nothing here enforces
# these values at runtime (guard.py / requester.py still read the DB directly, same
# as before Phase 1).
# ---------------------------------------------------------------------------------
EXPECTED_PROFILE_POLICY = {
    "requester_signature_required": 1,
    "approver_signature_policy": "All Approval Levels",
    "provider_creation_trigger": "Before First Signing Level",
}

# ---------------------------------------------------------------------------------
# Steps, in the order they actually run for a Payment Request. package_entry/exit and
# dsr_entry/exit reference ecentric_workspace.platform.esign.state statuses;
# the contract test proves every edge used below is one esign.state actually allows.
# ---------------------------------------------------------------------------------
STEPS = (
    step("document_setup", "Phân loại tài liệu cần ký",
         actor="requester",
         backed_by="esign.document_setup.set_document_requires_signature",
         package_entry=(None, "Draft"), package_exit="Draft",
         notes="Chỉ classify + tạo Draft package/DSF; chưa lock, chưa gọi SCTS."),

    step("signer_plan", "Xác định các vị trí cần ký (đọc, không ghi)",
         actor="system",
         backed_by="esign.signer_plan.resolve_signer_plan",
         notes="Không đổi state; hợp nhất Approval Engine level/participant + Profile policy."),

    step("placement", "Đặt vị trí chữ ký trên PDF",
         actor="requester",
         backed_by="esign.placement_service.save_placement",
         package_entry="Draft", package_exit="Draft",
         notes=("Ghi có phạm vi theo từng file (File A không đụng File B). Placement "
                "còn thiếu chỉ lộ ra dưới dạng DSR 'Placement Required' ở bước ký kế "
                "tiếp (requester_sign/approver_sign), không phải ở đây - vì DSR chưa "
                "tồn tại tại bước này.")),

    step("package_lock", "Khoá package (đóng băng nội dung + hash)",
         actor="requester",
         backed_by="esign.package.lock_package",
         package_entry="Draft", package_exit="Locked",
         notes="package_hash pin đúng nội dung sẽ ký; đổi sau đó bắt buộc version mới."),

    step("requester_sign", "Người đề nghị Submit & Sign (Option B, mở khoá Level 1)",
         actor="requester",
         backed_by="esign.requester.*  (submit_and_sign / activate Level 1)",
         package_entry=("Locked", "Active"), package_exit="Active",
         dsr_entry="Draft", dsr_exit="Approval Completed",
         park=("Mapping Required", "Placement Required", "Retryable Failure",
                "Permanent Failure", "Verification Mismatch", "Manual Review"),
         notes=("CHỈ tồn tại khi Profile.requester_signature_required=1. KHÔNG phải "
                "một Approval Level - request đã đóng băng nhưng Level 1 chưa có ToDo "
                "cho tới khi DSR (actor_type=Requester) này Approval Completed. "
                "'Mapping Required'/'Placement Required' xuất hiện ở đây (DSR mới "
                "chuyển từ Prepared) dù nguyên nhân gốc là thiếu cấu hình ở các bước "
                "trước.")),

    step("provider_create", "Tạo tài liệu ký trên SCTS (AddDocument)",
         actor="system",
         backed_by="esign.tasks.process_signing_request",
         package_entry=("Locked", "Provider Creating", "Provider Created"),
         package_exit="Active",
         park=("Provider Create Failed",),
         notes=("Thời điểm chạy phụ thuộc provider_creation_trigger. Với "
                "'Before First Signing Level' (EXPECTED_PROFILE_POLICY ở trên), việc "
                "này chạy lồng bên trong lần ký ĐẦU TIÊN (requester_sign hoặc "
                "approver_sign level đầu), không phải một lệnh gọi riêng của người "
                "dùng - liệt kê tách bạch ở đây chỉ để dễ đọc thứ tự.")),

    step("approver_sign", "Người duyệt Duyệt & Ký (mỗi cấp yêu cầu ký)",
         actor="approver",
         backed_by="esign.service.approve_and_sign -> orchestrator -> guard.assert_level_completable",
         dsr_entry="Draft", dsr_exit="Approval Completed",
         park=("Mapping Required", "Placement Required", "Retryable Failure",
                "Permanent Failure", "Verification Mismatch", "Manual Review"),
         notes=("Lặp lại cho MỖI level mà guard.level_requires_signature()=True (Approval "
                "Engine vẫn sở hữu approver/thứ tự/hoàn tất - flow chỉ mô tả, không "
                "thay thế). Với approver_signature_policy=All Approval Levels thì đây "
                "là toàn bộ 4 cấp.")),

    step("verify", "Poll + xác thực trạng thái chữ ký với provider",
         actor="system",
         backed_by="esign.orchestrator.poll_provider_request -> service.verify_and_complete",
         dsr_entry=("Queued", "Provider Accepted", "Verifying"), dsr_exit="Signed",
         park=("Retryable Failure", "Permanent Failure", "Verification Mismatch"),
         notes="Poll-first: không bao giờ resubmit mù một lần thử còn mơ hồ."),

    step("retrieve_signed", "Tải + lưu PDF đã ký (sau khi cấp cuối cùng hoàn tất)",
         actor="system",
         backed_by="esign.signed_files.retrieve_and_store_for_package",
         package_entry="Active", package_exit="Active",
         park=(),
         notes=("GHI CHÚ TRUNG THỰC (2026-08-18): esign.state khai báo PACKAGE 'Completed' "
                "là trạng thái cuối, nhưng không tìm thấy nơi nào trong code hiện tại "
                "set package status = 'Completed' - package ở lại 'Active' sau khi ký "
                "xong. Đây là quan sát, KHÔNG phải hành vi flow này áp đặt; không sửa "
                "ở Phase 1.")),
)

STEP_BY_ID = {s.id: s for s in STEPS}
