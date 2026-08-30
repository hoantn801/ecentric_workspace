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


