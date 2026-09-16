"""Immutable contract implemented by every Approval Center request type."""
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Tuple


FilterBuilder = Callable[[dict, dict], None]
OptionsProvider = Callable[[], dict]
TitleBuilder = Callable[[object], str]
Submitter = Callable[[str], str]
Resubmitter = Callable[[str, Optional[str]], dict]

STANDARD_STATUS_LABELS = (
    ("Draft", "Nháp"),
    ("Pending", "Đang phê duyệt"),
    ("Information Required", "Cần bổ sung"),
    ("Approved", "Đã duyệt"),
    ("Rejected", "Bị từ chối"),
    ("Cancelled", "Đã hủy"),
)


@dataclass(frozen=True, slots=True)
class ApprovalDefinition:
    """Stateless singleton configuration for one business request type.

    Values must be immutable. Callbacks receive all request-specific state as
    arguments and must never retain Documents, users, or request context.
    """

    code: str
    business_doctype: str
    editable_fields: Tuple[str, ...]
    my_request_fields: Tuple[str, ...]
    approval_list_fields: Tuple[str, ...]
    status_labels: Tuple[Tuple[str, str], ...]
    options_provider: OptionsProvider
    title_builder: Optional[TitleBuilder]
    submitter: Submitter
    resubmitter: Resubmitter
    filter_builder: Optional[FilterBuilder] = None
    max_page_length: int = 50
    approval_projection: str = "standard"
    draft_preparer: Optional[Callable] = None
    feature: str = ""
    #: Truong KHONG duoc chep khi "Tao phieu moi tu phieu nay".
    #:
    #: Danh cho cac o mang tinh CAM KET CA NHAN - nguoi dung tich vao de xac nhan mot dieu
    #: gi do. Chep nguyen mot lo cam ket sang phieu moi la ky thay ho: man hinh se noi ho
    #: "da xac nhan thong tin va tep dinh kem la chinh xac" cho mot bo ho so ho chua doc lai.
    #: De trong la mac dinh; module nao co o nhu vay thi tu khai ra.
    clone_exclude_fields: Tuple[str, ...] = ()
    #: Truong KHONG duoc de AI dien ho (du no nam trong `editable_fields`).
    #:
    #: Ba luat loai tru chay song song, khai o `shared/integrations/ai_formfill.build_schema`:
    #:   1. kieu truong  - tep dinh kem, bang con, chu ky, va MOI `Check` (o tick nao cung la
    #:      mot khang dinh cua nguoi dung, khong phai du kien doc duoc tu ho so);
    #:   2. `clone_exclude_fields` - dung lai NGUYEN SI. Tuple do da duoc dinh nghia dung la
    #:      "o cam ket ca nhan, chep sang la ky thay nguoi dung". AI dien vao do cung la ky
    #:      thay, cung mot ly do;
    #:   3. tuple NAY - cho truong khong phai tep, khong phai cam ket, nhung van phai do
    #:      nguoi lam: phan doan nghiep vu (`is_cost_valid`), o keo theo mot picker co phan
    #:      quyen (`funding_source_*`), hay o ma gui di se TAO mot ban ghi danh muc moi
    #:      (`ec_brand_ten`).
    ai_exclude_fields: Tuple[str, ...] = ()
    #: Khoi doc them cho man hinh chi tiet, do module so huu: (business_doc, approval_request)
    #: -> dict, gan vao detail["extra"]. Dung khi form can ngu canh ngoai phieu (Payment Request:
    #: chuoi cac dot thanh toan). Chi DOC; khong ghi, khong giu tham chieu.
    detail_extender: Optional[Callable] = None

    @property
    def status_label_map(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.status_labels))


def validate_definition(definition: ApprovalDefinition) -> None:
    """Raise ValueError when a registered definition violates the ADR contract."""
    if not isinstance(definition, ApprovalDefinition):
        raise ValueError("request definition must be an ApprovalDefinition")
    if not definition.code or not definition.business_doctype:
        raise ValueError("request definition requires code and business_doctype")
    if definition.max_page_length < 1:
        raise ValueError("max_page_length must be positive")
    if definition.approval_projection not in ("standard", "legacy_level_name"):
        raise ValueError("unsupported approval_projection")
    for item in fields(definition):
        value = getattr(definition, item.name)
        if isinstance(value, (list, dict, set)):
            raise ValueError("mutable definition field: %s" % item.name)
    for callback_name in ("options_provider", "submitter", "resubmitter"):
        if not callable(getattr(definition, callback_name)):
            raise ValueError("definition callback is not callable: %s" % callback_name)
    if definition.title_builder is not None and not callable(definition.title_builder):
        raise ValueError("definition callback is not callable: title_builder")
    if definition.draft_preparer is not None and not callable(definition.draft_preparer):
        raise ValueError("definition callback is not callable: draft_preparer")
    if definition.detail_extender is not None and not callable(definition.detail_extender):
        raise ValueError("definition callback is not callable: detail_extender")


