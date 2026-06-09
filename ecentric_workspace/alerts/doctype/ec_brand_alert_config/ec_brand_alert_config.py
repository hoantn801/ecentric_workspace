# Copyright (c) 2026, eCentric
# Alert Center Phase G1.1 - brand-level COMPONENT-BASED price evaluation basis.
# Each brand ticks which discount components are subtracted from RSP for the
# min-price compliance check (include_seller_discount / include_seller_voucher
# / include_platform_discount / include_platform_voucher /
# use_customer_paid_if_available). Kept SEPARATE from EC Brand Integration
# Settings so BIS stays integration/credential-focused. SM-only DocPerm;
# managed through the service layer (api_brands).

from frappe.model.document import Document

# default (no config row) = seller-funded: seller discount + seller voucher,
# platform components OFF. Preserves legacy behavior.
DEFAULT_FLAGS = {
    "include_seller_discount": 1,
    "include_seller_voucher": 1,
    "include_platform_discount": 0,
    "include_platform_voucher": 0,
    "use_customer_paid_if_available": 0,
}


class ECBrandAlertConfig(Document):
    pass
