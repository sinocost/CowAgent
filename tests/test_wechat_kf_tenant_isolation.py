# encoding:utf-8
"""End-to-end privacy boundaries for WeChat Customer Service tenants."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel
from channel.wechat_kf.tenant_identity import (
    delivery_binding,
    session_key,
    user_key,
)
from channel.wechat_kf.wechat_kf_channel import WechatKfChannel


def test_pseudonymous_keys_are_stable_and_service_scoped():
    key = "installation-secret"
    first = user_key(key, "corp", "kf-a", "raw-user-a")

    assert first == user_key(key, "corp", "kf-a", "raw-user-a")
    assert first != user_key(key, "corp", "kf-a", "raw-user-b")
    assert first != user_key(key, "corp", "kf-b", "raw-user-a")
    assert "raw-user-a" not in first
    assert session_key(key, "corp", "kf-a", "raw-user-a") != first


def test_chat_channel_binds_explicit_tenant_owner_to_runtime_identity():
    context = Context(
        ContextType.TEXT,
        "hello",
        {"agent_id": "primary", "session_id": "session", "user_id": "tenant"},
    )

    identity = ChatChannel._identity_for(object.__new__(ChatChannel), context)

    assert identity.agent_id == "primary"
    assert identity.session_id == "session"
    assert identity.user_id == "tenant"


def _bare_channel():
    cls = WechatKfChannel.__wrapped__
    channel = cls.__new__(cls)
    channel.tenant_key = "installation-secret"
    channel.client = MagicMock()
    return channel


def test_inbound_reply_ignores_mutable_context_recipient_override():
    channel = _bare_channel()
    channel._send_text = MagicMock()
    msg = SimpleNamespace(external_userid="original-user", open_kfid="kf-a")
    context = Context(ContextType.TEXT, "hello", {
        "receiver": "original-user",
        "external_userid": "wrong-user",
        "open_kfid": "kf-b",
        "msg": msg,
        "wechat_kf_delivery_binding": delivery_binding(
            channel.tenant_key, "kf-a", "original-user"
        ),
    })

    channel.send(Reply(ReplyType.TEXT, "answer"), context)

    channel._send_text.assert_called_once_with("original-user", "kf-a", "answer")


def test_delivery_binding_mismatch_blocks_send():
    channel = _bare_channel()
    channel._send_text = MagicMock()
    msg = SimpleNamespace(external_userid="user-b", open_kfid="kf-a")
    context = Context(ContextType.TEXT, "hello", {
        "receiver": "user-b",
        "msg": msg,
        "wechat_kf_delivery_binding": delivery_binding(
            channel.tenant_key, "kf-a", "user-a"
        ),
    })

    channel.send(Reply(ReplyType.TEXT, "must not leave"), context)

    channel._send_text.assert_not_called()
