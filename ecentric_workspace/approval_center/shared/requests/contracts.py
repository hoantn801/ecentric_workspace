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
    ("Draft", "NhÃ¡p"),
    ("Pending", "Äang phÃª duyá»‡t"),
    ("Information Required", "Cáº§n bá»• sung"),
    ("Approved", "ÄÃ£ duyá»‡t"),
    ("Rejected", "Bá»‹ tá»« chá»‘i"),
    ("Cancelled", "ÄÃ£ há»§y"),
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


