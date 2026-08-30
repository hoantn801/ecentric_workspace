# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the send-back banner reads straight.

The "Cần bổ sung thông tin" banner rendered with its icon floating in the middle and the text
pushed to the right edge. The icon is an inline <svg> that took its size from
`#ec-payr-root .icon{width:18px}` - a scoped rule. Where the banner renders outside that
ancestor, the rule does not reach it, the SVG falls back to the browser default of 300x150px,
and a 300px-wide box shoves the sentence across the card.

Both banner icons now carry width/height on the element itself. A component should not depend
on where in the DOM it happens to be mounted - the same lesson as the CSS rule that hid the
attachment field and the site-wide form kit that stacked a second dropzone on this page.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
