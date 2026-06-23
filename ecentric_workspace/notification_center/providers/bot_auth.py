# Copyright (c) 2026, eCentric and contributors
"""Inbound Microsoft Bot Connector authentication for the Teams messaging endpoint.

Validates the `Authorization: Bearer <JWT>` that the Bot Connector service attaches to every
inbound activity, against the public Bot Connector OpenID metadata + signing keys (JWKS).
Uses PyJWT (+ cryptography) -- a well-maintained library compatible with Frappe v16/Python --
for RS256 signature verification; no hand-rolled crypto. There is NO config switch to disable
validation.

Checks: bearer present; RS256 signature against the Bot Connector JWKS; issuer (from metadata);
audience == the bot's Microsoft App ID; exp/iat (+ nbf if present); serviceUrl claim == the
incoming activity's serviceUrl; Teams channel endorsement on the signing key.

Secrets/tokens are never logged (callers log only a short reason code).
"""
import json
import time

OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
_DEFAULT_ISSUER = "https://api.botframework.com"
_CACHE = {}                 # url -> (expires_ts, data)
_CACHE_TTL = 24 * 3600
TIMEOUT = 10


def _fetch_json(url):
    import requests
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _cached(url):
    now = time.time()
    hit = _CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    data = _fetch_json(url)
    _CACHE[url] = (now + _CACHE_TTL, data)
    return data


def _get_metadata():
    return _cached(OPENID_URL)


def _get_jwks(jwks_uri):
    return _cached(jwks_uri)


def validate_bot_request(auth_header, activity, app_id):
    """Validate an inbound Bot Connector request. Returns (ok: bool, reason: str)."""
    if not app_id:
        return False, "no_app_id"
    if not auth_header or not str(auth_header).startswith("Bearer "):
        return False, "missing_bearer"
    token = str(auth_header)[7:].strip()
    if not token:
        return False, "empty_token"

    import jwt
    from jwt.algorithms import RSAAlgorithm
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return False, "bad_header"
    kid = header.get("kid")
    if not kid:
        return False, "no_kid"

    try:
        md = _get_metadata()
        jwks = _get_jwks(md.get("jwks_uri"))
    except Exception:
        return False, "metadata_unavailable"

    jwk = next((k for k in (jwks.get("keys") or []) if k.get("kid") == kid), None)
    if not jwk:
        return False, "unknown_kid"

    # Teams channel endorsement: the activity must arrive over a channel the key endorses.
    channel = (activity or {}).get("channelId")
    endorsements = jwk.get("endorsements") or []
    if channel and endorsements and channel not in endorsements:
        return False, "channel_not_endorsed"

    try:
        key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    except Exception:
        return False, "bad_jwk"

    issuer = md.get("issuer") or _DEFAULT_ISSUER
    try:
        claims = jwt.decode(
            token, key=key, algorithms=["RS256"], audience=app_id, issuer=issuer,
            leeway=300, options={"require": ["exp", "iat", "aud", "iss"]})
    except Exception as e:
        return False, "jwt_" + type(e).__name__

    su = claims.get("serviceurl") or claims.get("serviceUrl")
    act_su = (activity or {}).get("serviceUrl")
    if su and act_su and su != act_su:
        return False, "serviceurl_mismatch"

    return True, "ok"
