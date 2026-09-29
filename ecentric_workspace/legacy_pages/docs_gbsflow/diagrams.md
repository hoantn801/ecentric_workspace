# /docs/gbs-flow — nguồn 3 sơ đồ

Trang hiển thị 3 sơ đồ dưới dạng **SVG vẽ sẵn** trong `main_section.html` (brief `NHIEU_LOP/brief_gbs.md` mục 5:
nội dung tài liệu nằm sẵn trong HTML, không vẽ lại bằng JS lúc tải). Trước 29/09/2026 trang nạp mermaid 10.9 từ CDN
rồi vẽ đè lên khối `<pre class="mermaid">`, nên người xem thấy mã nguồn sơ đồ rồi mới thấy hình.

## Sửa một sơ đồ

1. Sửa khối mermaid tương ứng bên dưới.
2. Vẽ lại bằng mermaid **10.9**, cấu hình như trang cũ: `theme: 'neutral'`,
   `flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' }`,
   `sequence: { useMaxWidth: true, showSequenceNumbers: false }`. Vẽ trên trình duyệt Windows/Mac
   (chữ đo bằng font Trebuchet MS — vẽ trên máy thiếu font này thì khung chữ lệch).
3. Lấy `outerHTML` của `<svg>`, bỏ thuộc tính `data-*` và các `<symbol>` không có `<use>` trỏ tới, rồi thay
   nội dung khối `<pre class="gfd-mmd">…</pre>` tương ứng trong `main_section.html`.
4. Làm đủ 3 bước resync (patch → `patches.txt` → `sha256` trong `resync_manifest.json`) và bump
   `BASELINE_SHA256` trong `page_sync.py`.

## Tổng quan — sơ đồ tổng thể (tab "Tổng quan")

```mermaid
flowchart LR
    Start([Bắt đầu]):::startNode --> Create[User tạo SO/PO trên form]
    Create --> FinReview{Finance review}
    FinReview -->|Phê duyệt| Sync[Sync sang GBS]
    FinReview -->|Send back| CanSua[Trạng thái Cần sửa]
    CanSua --> EditForm[User chỉnh sửa form]
    EditForm --> Resubmit[Submit lại]
    Resubmit --> FinReview
    Sync --> GBSReview[GBS Verifier/Manager review]
    GBSReview -->|Approve| Done([Approved - To Bill]):::endNode
    GBSReview -->|Reject| GBSReject[GBS Rejected]
    GBSReject --> Resubmit
    classDef startNode fill:#d1fae5,stroke:#10b981
    classDef endNode fill:#fce7f3,stroke:#ec4899
```

## Happy path (tab "Happy path")

```mermaid
stateDiagram-v2
    [*] --> Pending : User submit form
    Pending --> Approved : Finance approve
    Pending --> CanSua : Finance send back
    CanSua --> Pending : User edit + resubmit
    Approved --> GBSDraft : Sync POST
    GBSDraft --> GBSPendingManager : Auto Submit for Approval (Services)
    GBSPendingManager --> GBSApproved : Manager approve
    GBSPendingManager --> GBSRejected : Manager reject
    GBSRejected --> Approved : User resubmit cycle
    GBSApproved --> [*] : Invoice ready

    state CanSua {
      [*] --> ClickResubmit
      ClickResubmit --> FormEdit
      FormEdit --> SubmitAgain
      SubmitAgain --> [*]
    }
```

## Error & edge cases (tab "Error & Edge cases")

```mermaid
sequenceDiagram
    autonumber
    actor User
    actor Finance
    participant eCentric
    participant Sync as Sync v13
    participant Boxme

    Boxme->>eCentric: Rejected (qua poll)
    User->>eCentric: Click Resubmit
    eCentric->>User: Redirect form edit
    User->>eCentric: Edit + Submit lại
    eCentric->>Finance: Status Pending
    Finance->>eCentric: Approve
    eCentric->>Sync: Trigger
    Sync->>Boxme: apply_workflow Resubmit
    Boxme-->>Sync: Rejected → Draft
    Note over Sync: Settle loop 1s (race defense)
    Sync->>Boxme: PUT updated fields
    Boxme-->>Sync: 200 OK
    Sync->>Boxme: apply Submit for Approval
    Boxme-->>Sync: Draft → Pending Manager
```
