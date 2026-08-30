"""Single stateless entry point used by all vertical approval modules."""
from dataclasses import dataclass

from ecentric_workspace.approval_center.shared.requests import capabilities
from ecentric_workspace.approval_center.shared.requests import command_service
from ecentric_workspace.approval_center.shared.requests import fulfillment_service
from ecentric_workspace.approval_center.shared.requests import query_service


@dataclass(frozen=True, slots=True)
class ApprovalFacade:
    """Immutable facade; request/user state is always passed as arguments."""

    def bootstrap(self, definition):
        return query_service.bootstrap(definition)

    def options(self, definition):
        return definition.options_provider()

    def list_my_requests(self, definition, filters=None, start=0, page_length=20):
        return query_service.list_my_requests(definition, filters, start, page_length)

    def list_my_approvals(self, definition, section="pending"):
        return query_service.list_my_approvals(definition, section)

    def detail(self, definition, name):
        return query_service.detail(definition, name)

    def save_draft(self, definition, name=None, payload=None):
        return command_service.save_draft(definition, name, payload)

    def submit(self, definition, name):
        return command_service.submit(definition, name)

    def clone_request(self, definition, name):
        return command_service.clone_request(definition, name)

    def approve(self, definition, name, comment=None):
        return command_service.approve(definition, name, comment)

    def reject(self, definition, name, comment=None):
        return command_service.reject(definition, name, comment)

    def request_information(self, definition, name, comment=None):
        return command_service.request_information(definition, name, comment)

    def resubmit(self, definition, name, payload=None):
        return command_service.resubmit(definition, name, payload)

    def cancel(self, definition, name, reason=None):
        return command_service.cancel(definition, name, reason)

    def admin_approve_current_level(self, definition, name, reason=None):
        return command_service.admin_approve_current_level(definition, name, reason)

    def approve_with_operation_date(self, definition, name, comment=None, operation_date=None):
        return command_service.approve_with_operation_date(
            definition, name, comment, operation_date)

    def list_fulfillment_queue(self, definition, section, fields, order_by):
        return fulfillment_service.list_queue(definition, section, fields, order_by)

    def claim_fulfillment(self, definition, name):
        return fulfillment_service.claim(definition, name)

    def complete_fulfillment(self, definition, name, payload=None):
        return fulfillment_service.complete(definition, name, payload)

    def resolve_request(self, definition, name):
        return command_service.resolve_request(definition, name)

    def process_preview(self, code):
        return query_service.process_preview(code)

    def employee_context(self, user=None):
        return query_service.employee_context(user)

    @property
    def capabilities(self):
        return capabilities

APPROVAL_FACADE = ApprovalFacade()


