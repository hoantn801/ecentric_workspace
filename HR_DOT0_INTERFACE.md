# Đợt 0 — Hợp đồng engine cho feature HR (Agent A, 23/11/2026)

Nhánh `feat/hr-dot0-nen-engine`. Mọi feature mới (Offer V2, Nghỉ việc/Clearance V2, Đánh giá, Kỷ luật…) **chỉ khai báo**, không tự code lại các luật dưới đây.

## 1. Phiếu riêng tư — `private`
```python
MY_DEFINITION = ApprovalDefinition(..., private=True)   # shared/requests/contracts.py
```
- Hoặc cấu hình: `EC Approval Type.private = 1` (OR với cờ code; không tắt được cờ code từ màn hình).
- Ai xem: người gửi · người có dòng duyệt trong snapshot · người theo dõi · người xử lý (fulfillment_owner / Fulfiller cấu hình / ToDo trên chính phiếu) · người có quyền đọc qua Gắn phiếu · System Manager (mở bằng link, **luôn** ghi `EC Approval Access Log`).
- Bị loại khỏi: trưởng phòng, Approval Admin, tab "Tất cả" (hub + tab từng form), Thống kê, export, bộ lọc. Áp cho mọi tầng `reporting.scope.scope_predicate` (kể cả admin). Luật duy nhất: `shared/workflow/privacy.py` (`is_private_type`, `scope_sql`, `note_access`).
- Patch nên đặt `EC Approval Type.private=1` cho loại của mình để quản trị nhìn thấy (không bắt buộc).

## 2. Người theo dõi — `participant_purpose="Notify"`
- Khai trong setup process: thêm dòng `EC Approval Participant` với `participant_purpose="Notify"` ở **process** (`proc.participants`) hoặc ở **level**. Mọi `source_type` đều dùng được (`Role` EC CEO, `User`, `Reference User Field`…), giải bằng `resolve_participants` lúc gửi → chốt vào `EC Approval Request Watcher` (snapshot, phiếu đang chạy không đổi).
  ```python
  proc.append("participants", {"participant_purpose": "Notify", "source_type": "Role", "role": "EC CEO", "sort_order": 9})
  ```
- Thêm động theo điều kiện nghiệp vụ (sau `engine.submit`): `transitions.add_watchers(request_name, ["user@x"], actor=..., source="CEO theo dõi")` (không whitelist).
- Hành vi: đọc phiếu + tải tệp (DocShare như người duyệt); thông báo `severity="info"` lúc **gửi / từ chối / yêu cầu bổ sung / huỷ / duyệt xong**; **không** có nút duyệt, không thêm tệp. Bỏ qua người gửi và người đã là người duyệt.
- Ẩn trường nhạy cảm với người chỉ theo dõi: `ApprovalDefinition(watcher_hidden_fields=("compensation",))`.
- Mục "Tôi theo dõi": `reporting.api.list_requests(box="watching")`; chi tiết trả `detail["privacy"] = {private, watchers, i_am_watcher, access_log}`.

## 3. Chặn tự duyệt — `subject_fields`
```python
ApprovalDefinition(..., subject_fields=("employee_email",))   # email/User hoặc mã Employee
```
- Lúc gửi, engine loại **người gửi + đối tượng** khỏi mọi cấp (kể cả qua Role). Cấp còn người khác → bỏ người đó. Cấp rỗng → `fallback_user` của dòng → (luồng ký số: giữ nguyên + Error Log) → bỏ cấp, sang cấp kế → cấp cuối: quản lý trực tiếp của người gửi → không ai: chặn gửi với câu hướng dẫn. Each Group: nhóm rỗng → fallback, không có thì giữ + ghi chú. Mọi quyết định ghi `EC Approval Action` "Skipped" ("Chặn tự duyệt: …").
- Feature muốn **giữ** cấp LM khi LM = CEO: không dính luật này (luật chỉ loại người gửi/đối tượng); việc gộp người trùng cấp vẫn là `_skip_earlier_duplicate_levels` như cũ.

## 4. Chuyển người duyệt khi nghỉ việc / bị khoá — tự động
- Không cần khai báo. User bị khoá (hook `User.on_update`) + job 00:45 (`approver_handover.sweep`): dòng Pending → người khác cùng role / quản lý của người đó / `fallback_user` của cấp; không ai → giữ + Error Log. Audit `Reassigned`.
- Feature tự gọi được: `transitions.reassign_pending_approver(row_name, [new_user], actor, reason, require_target=True)`.
- System Manager chuyển tay: `approval_center.shared.workflow.approver_handover.reassign_approver(request_name, old_user, new_user, reason)` (POST).

## 5. Mức gấp — `urgency` / `severity`
- DocType nghiệp vụ có trường **`urgency`** (Select, giá trị `Bình thường` / `Gấp`) → mọi thông báo "Cần duyệt" của engine tự đi `severity="urgent"` (xuyên giờ yên lặng 21h–9h). Giá trị gấp: `transitions.URGENT_VALUES`.
- Gọi tay: `transitions.notify(users, subject, doctype, name, severity="urgent")` (`None` = mặc định cũ; `"info"` = tin theo dõi).
- SLA riêng từng phiếu (vd Gấp 4 giờ LV, hay NV 2 vs 3 ngày theo loại đánh giá): `engine.submit(..., sla_overrides={level_no: "POLICY_CODE"})` — chốt vào snapshot trước khi kích hoạt cấp; policy không có/không active thì giữ SLA của process.

## 6. Gắn phiếu duyệt — không cần khai báo
- Asset dùng chung `ec_approval_links.bundle.js` hiện chip + nút "+ Gắn phiếu duyệt" trong khu Hành động của **mọi** form (qua `EcRemind.buttonHTML(cap)`), theo `capabilities.approval_links`. Endpoint: `approval_center.reporting.actions.search_linkable / link_approval / unlink_approval / set_link_override_reason / list_approval_links`.
- Server chặn gửi khi phiếu gắn bị Từ chối/Huỷ mà chưa ghi lý do: feature mới nên gọi `approval_links.assert_host_submittable(doctype, name)` trong `submit()` (engine đã gọi sẵn cho 34 form qua `command_service.submit/resubmit`).
- Đọc phiếu gắn từ code: `approval_links.links_for_host(doctype, name, viewer)` (đã lọc nhãn an toàn).
