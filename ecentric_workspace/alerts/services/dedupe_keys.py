"""Dedupe key builders. PURE module (no frappe).

Decision C1 (2026-06-07) - dual tier:
  * transaction-level price incidents -> order-line keys
  * master-data alerts (missing_policy / missing_brand_mapping) -> daily
    SKU-level keys with {YYYYMMDD} in site timezone (Asia/Ho_Chi_Minh);
    the caller passes yyyymmdd derived from frappe.utils.nowdate().
EC Alert.dedupe_key / EC Alert Action.dedupe_key are Data(140) UNIQUE, so
keys longer than 140 chars are compacted deterministically (_fit).
"""
import hashlib

MAX_LEN = 140


def price_alert_key(external_order_id, external_line_id, rule_code):
    return _fit("omisell|%s|%s|price|%s" % (_s(external_order_id), _s(external_line_id), _s(rule_code)))


def lock_action_key(external_order_id, external_line_id, rule_code):
    return _fit("omisell|%s|%s|stock_safety_lock|%s" % (_s(external_order_id), _s(external_line_id), _s(rule_code)))


def occurrence_key(external_order_id, external_line_id, rule_code):
    """G1.1: per-order-line price-violation evidence key (EC Alert Occurrence).
    One immutable row per (order, line, rule); re-pull of the same line is a
    no-op, a different order/line is a new occurrence."""
    return _fit("omisell|%s|%s|occ|%s" % (
        _s(external_order_id), _s(external_line_id), _s(rule_code)))


def case_key(brand, platform, shop, seller_sku, rule_code,
             external_order_id, external_line_id):
    """G1.1 Case identity - FIXED 2026-06-11: now includes platform + shop.

    Bug: the original key (and the open-case lookup) grouped by
    brand+sku+rule only, so a Lazada occurrence attached to an open Shopee
    case (EC-AL-000708). One open Case per
    brand+platform+shop+seller_sku+rule_code; first order/line make the key
    unique across case generations of the same scope."""
    return _fit("case|%s|%s|%s|%s|%s|%s|%s" % (
        _s(brand), _s(platform), _s(shop), _s(seller_sku), _s(rule_code),
        _s(external_order_id), _s(external_line_id)))


def missing_policy_key(brand, platform, shop, seller_sku, yyyymmdd, external_product_id=None):
    if external_product_id:
        return _fit("omisell|%s|%s|%s|%s|%s|missing_policy|%s" % (
            _s(brand), _s(platform), _s(shop), _s(external_product_id), _s(seller_sku), _s(yyyymmdd)))
    return _fit("omisell|%s|%s|%s|%s|missing_policy|%s" % (
        _s(brand), _s(platform), _s(shop), _s(seller_sku), _s(yyyymmdd)))


def missing_brand_mapping_key(platform, shop, seller_sku, yyyymmdd, external_product_id=None):
    if external_product_id:
        return _fit("omisell|%s|%s|%s|%s|missing_brand_mapping|%s" % (
            _s(platform), _s(shop), _s(external_product_id), _s(seller_sku), _s(yyyymmdd)))
    return _fit("omisell|%s|%s|%s|missing_brand_mapping|%s" % (
        _s(platform), _s(shop), _s(seller_sku), _s(yyyymmdd)))


def ingestion_failed_key(brand, yyyymmdd):
    """Daily per-brand key for ingestion_api_failed (decision Q-D3)."""
    return _fit("omisell|%s|ingestion_api_failed|%s" % (_s(brand), _s(yyyymmdd)))


def missing_credential_key(brand, yyyymmdd):
    """Daily per-brand key for missing_integration_credential (format proposed
    in 05_PHASE_C_REPORT - not part of the user-specified C1 list)."""
    return _fit("omisell|%s|missing_integration_credential|%s" % (_s(brand), _s(yyyymmdd)))


def min_window_capped_key(brand, window, cap, yyyymmdd):
    """Adaptive pull (2026-06-14): per brand + stuck sub-window + cap + day, so a
    minimum-width window that still exceeds cap raises ONE alert, not one per
    scheduler cycle. `window` = '<epoch_from>_<epoch_to>' of the stuck leaf."""
    return _fit("omisell|%s|min_window_capped|%s|%s|%s" % (
        _s(brand), _s(window), _s(cap), _s(yyyymmdd)))


def _s(v):
    return "" if v is None else str(v).strip()


def _fit(key):
    if len(key) <= MAX_LEN:
        return key
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:32]
    return key[: MAX_LEN - 33] + "#" + digest
