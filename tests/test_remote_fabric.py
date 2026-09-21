from __future__ import annotations

import pytest

from wexspace_human_governed_core.remote_fabric import (
    AuthorityGrant,
    AuthorityRegistry,
    ControlLane,
    DeviceEndpoint,
    DeviceKind,
    DeviceRegistry,
    GrantMode,
    OpenAINativeRemoteCompatibilityProbe,
    PairingBroker,
    RemoteRoutePlanner,
    sanitize_capabilities,
)


def test_pairing_ticket_roundtrip_and_single_use():
    now = 1_800_000_000
    broker = PairingBroker(b"x" * 32, clock=lambda: now)
    ticket = broker.issue(
        target_device_id="phone-1",
        controller_device_id="pc-1",
        requested_lane=ControlLane.WEXSPACE_ANDROID_MCP,
        ttl_seconds=120,
    )
    payload = broker.verify_and_consume(ticket.token)
    assert payload["target"] == "phone-1"
    assert payload["controller"] == "pc-1"
    assert payload["lane"] == "wexspace_android_mcp"
    with pytest.raises(ValueError, match="already consumed"):
        broker.verify_and_consume(ticket.token)


def test_pairing_ticket_rejects_tamper():
    broker = PairingBroker(b"x" * 32, clock=lambda: 1_800_000_000)
    ticket = broker.issue(
        target_device_id="phone-1",
        controller_device_id="pc-1",
        requested_lane=ControlLane.WEXSPACE_PAIRING,
    )
    head, sig = ticket.token.split(".", 1)
    tampered = ("A" if head[0] != "A" else "B") + head[1:] + "." + sig
    with pytest.raises(ValueError):
        broker.verify_and_consume(tampered)


def test_pairing_ticket_rejects_expired():
    clock = {"now": 1_800_000_000}
    broker = PairingBroker(b"x" * 32, clock=lambda: clock["now"])
    ticket = broker.issue(
        target_device_id="phone-1",
        controller_device_id="pc-1",
        requested_lane=ControlLane.WEXSPACE_PAIRING,
        ttl_seconds=15,
    )
    clock["now"] += 16
    with pytest.raises(ValueError, match="expired"):
        broker.verify_and_consume(ticket.token)


def test_android_gemini_prefers_custom_mcp():
    devices = DeviceRegistry()
    devices.upsert(DeviceEndpoint(
        "phone", DeviceKind.ANDROID, "Phone", "owner", True,
        sanitize_capabilities(["mcp_server", "wexspace_pairing"])
    ))
    devices.upsert(DeviceEndpoint("pc", DeviceKind.WINDOWS, "PC", "owner", True))
    route = RemoteRoutePlanner(devices).choose(
        controller_device_id="pc",
        target_device_id="phone",
        client_surface="gemini_spark",
    )
    assert route.lane is ControlLane.GEMINI_CUSTOM_MCP


def test_chatgpt_mobile_prefers_openai_native_for_supported_desktop_host():
    devices = DeviceRegistry()
    devices.upsert(DeviceEndpoint("phone", DeviceKind.ANDROID, "Phone", "owner", True))
    devices.upsert(DeviceEndpoint(
        "pc", DeviceKind.WINDOWS, "PC", "owner", True,
        sanitize_capabilities(["openai_remote_host", "wexspace_pairing"])
    ))
    route = RemoteRoutePlanner(devices).choose(
        controller_device_id="phone",
        target_device_id="pc",
        client_surface="chatgpt_mobile",
    )
    assert route.lane is ControlLane.OPENAI_NATIVE_REMOTE


def test_windows_falls_back_to_wexspace_pairing_when_native_not_available():
    devices = DeviceRegistry()
    devices.upsert(DeviceEndpoint("phone", DeviceKind.ANDROID, "Phone", "owner", True))
    devices.upsert(DeviceEndpoint(
        "pc", DeviceKind.WINDOWS, "PC", "owner", True,
        sanitize_capabilities(["wexspace_pairing"])
    ))
    route = RemoteRoutePlanner(devices).choose(
        controller_device_id="phone",
        target_device_id="pc",
        client_surface="chatgpt_mobile",
    )
    assert route.lane is ControlLane.WEXSPACE_PAIRING


def test_offline_target_rejected():
    devices = DeviceRegistry()
    devices.upsert(DeviceEndpoint("phone", DeviceKind.ANDROID, "Phone", "owner", True))
    devices.upsert(DeviceEndpoint(
        "pc", DeviceKind.WINDOWS, "PC", "owner", False,
        sanitize_capabilities(["openai_remote_host"])
    ))
    with pytest.raises(ValueError, match="offline"):
        RemoteRoutePlanner(devices).choose(
            controller_device_id="phone",
            target_device_id="pc",
            client_surface="chatgpt_mobile",
        )


def test_authority_registry_uses_opaque_handles_and_scopes():
    reg = AuthorityRegistry()
    reg.upsert(AuthorityGrant(
        grant_id="g1",
        provider="google_drive",
        principal="owner",
        modes=frozenset({GrantMode.READ, GrantMode.WRITE}),
        scopes=frozenset({"files.read", "files.write"}),
        opaque_authority_handle="vault://google-drive/main",
        device_ids=frozenset({"pc-1", "phone-1"}),
    ))
    assert reg.find(
        provider="google_drive",
        principal="owner",
        mode=GrantMode.WRITE,
        scope="files.write",
        device_id="phone-1",
    )
    assert not reg.find(
        provider="google_drive",
        principal="owner",
        mode=GrantMode.ADMIN,
        scope="files.write",
        device_id="phone-1",
    )


def test_capability_sanitizer_rejects_secretish_content():
    with pytest.raises(ValueError, match="secret material"):
        sanitize_capabilities(["mcp_server", "token=abc"])


def test_openai_probe_fingerprints_uri_without_contacting_provider():
    obs = OpenAINativeRemoteCompatibilityProbe.observe_pairing_payload(
        "https://example.invalid/pair/opaque-id"
    )
    assert obs.payload_kind == "uri"
    assert obs.scheme == "https"
    assert obs.host == "example.invalid"
    assert obs.path == "/pair/opaque-id"
    assert len(obs.fingerprint_sha256) == 64


def test_openai_probe_handles_opaque_payload():
    obs = OpenAINativeRemoteCompatibilityProbe.observe_pairing_payload("PAIR-CODE-1234")
    assert obs.payload_kind == "opaque"
    assert obs.host is None
