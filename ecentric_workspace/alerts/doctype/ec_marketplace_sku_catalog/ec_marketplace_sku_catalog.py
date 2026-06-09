# Copyright (c) 2026, eCentric
# Alert Center Phase G2.1 - order-derived marketplace SKU catalog (for Price
# Policy search/autofill). Upserted from EC Marketplace Order Item lines; never
# blindly appended. SM-only DocPerm; business access via whitelisted services.

from frappe.model.document import Document


class ECMarketplaceSKUCatalog(Document):
    pass
