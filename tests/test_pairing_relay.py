from __future__ import annotations

import pytest

from services.pairing_relay.core import PairingEnvelope, RendezvousStore


def test_create_claim_confirm_roundtrip():
    clock={"now": 1_800_000_000}
    store=RendezvousStore(clock=lambda:clock["now"])
    s=store.create(ttl_seconds=60)
    assert len(s.code)==6 and s.code.isdigit()
    claimed=store.claim(
        code=s.code,
        target_device_id="phone-1",
        public_key_fingerprint="sha256:abc",
        capabilities=["SCREEN_READ","UI_CONTROL","screen_read"],
    )
    assert claimed.state=="DEVICE_CLAIMED"
    assert claimed.target_capabilities==("screen_read","ui_control")
    paired=store.confirm(session_id=s.session_id,controller_nonce=s.controller_nonce)
    assert paired.state=="PAIRED"
    assert paired.consumed is True


def test_wrong_nonce_rejected():
    store=RendezvousStore(clock=lambda:1_800_000_000)
    s=store.create()
    store.claim(code=s.code,target_device_id="p",public_key_fingerprint="f",capabilities=[])
    with pytest.raises(PermissionError):
        store.confirm(session_id=s.session_id,controller_nonce="wrong")


def test_expired_code_rejected():
    clock={"now":1_800_000_000}
    store=RendezvousStore(clock=lambda:clock["now"])
    s=store.create(ttl_seconds=30)
    clock["now"]+=31
    with pytest.raises(KeyError):
        store.claim(code=s.code,target_device_id="p",public_key_fingerprint="f",capabilities=[])


def test_qr_envelope_does_not_contain_controller_nonce():
    store=RendezvousStore(clock=lambda:1_800_000_000)
    s=store.create()
    url=PairingEnvelope(b"k"*32).encode(s,"https://wexspace.example")
    assert url.startswith("https://wexspace.example/pair/")
    assert s.controller_nonce not in url
