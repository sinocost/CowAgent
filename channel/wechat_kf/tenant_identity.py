"""Pseudonymous tenant identities for the WeChat Customer Service channel.

Raw ``external_userid`` values are delivery addresses.  They must not double as
filesystem names, memory owners, or values propagated into tools.  This module
derives purpose-separated, installation-local identifiers with HMAC-SHA256.
"""

from __future__ import annotations

import hashlib
import hmac


class TenantIdentityError(ValueError):
    """Raised when a tenant identity cannot be derived safely."""


def _digest(key: str, purpose: str, *parts: str) -> str:
    if not key:
        raise TenantIdentityError("wechat_kf_tenant_key (or secret fallback) is required")
    if any(not str(part or "").strip() for part in parts):
        raise TenantIdentityError("tenant identity parts must be non-empty")
    payload = "\0".join((purpose, *(str(part).strip() for part in parts)))
    return hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def user_key(key: str, corp_id: str, open_kfid: str, external_userid: str) -> str:
    """Stable private-data owner, isolated by enterprise and service account."""
    return "wxkf_u_" + _digest(key, "user", corp_id, open_kfid, external_userid)[:32]


def session_key(key: str, corp_id: str, open_kfid: str, external_userid: str) -> str:
    """Conversation queue/runtime key; deliberately distinct from ``user_key``."""
    return "wxkf_s_" + _digest(key, "session", corp_id, open_kfid, external_userid)[:32]


def delivery_binding(key: str, open_kfid: str, external_userid: str) -> str:
    """Integrity tag binding an outbound reply to its original WeChat target."""
    return _digest(key, "delivery", open_kfid, external_userid)


def matches_delivery_binding(
    key: str,
    binding: str,
    open_kfid: str,
    external_userid: str,
) -> bool:
    if not binding:
        return False
    try:
        expected = delivery_binding(key, open_kfid, external_userid)
    except TenantIdentityError:
        return False
    return hmac.compare_digest(str(binding), expected)
