from __future__ import annotations

from wexspace_human_governed_core.remote_app_surface import RemoteFabricAppSurface
from wexspace_human_governed_core.remote_fabric import (
    AuthorityGrant,
    AuthorityRegistry,
    ControlLane,
    DeviceEndpoint,
    DeviceKind,
    DeviceRegistry,
    GrantMode,
    PairingBroker,
    sanitize_capabilities,
)


def make_surface():
    devices = DeviceRegistry()
    devices.upsert(DeviceEndpoint(
        "phone-1",
        DeviceKind.ANDROID,
        "Owner phone",
        "owner",
        True,
        sanitize_capabilities(["mcp_server", "wexspace_pairing"]),
    ))
    devices.upsert(DeviceEndpoint(
        "pc-1",
        DeviceKind.WINDOWS,
        "Owner PC",
        "owner",
        True,
        sanitize_capabilities(["openai_remote_host", "wexspace_pairing"]),
    ))
    auth = AuthorityRegistry()
    auth.upsert(AuthorityGrant(
        grant_id="drive-main",
        provider="google_drive",
        principal="owner",
        modes=frozenset({GrantMode.READ, GrantMode.WRITE}),
        scopes=frozenset({"files.read", "files.write"}),
        opaque_authority_handle="vault://google-drive/main",
        device_ids=frozenset({"phone-1", "pc-1"}),
    ))
    return RemoteFabricAppSurface(
        devices=devices,
        authorities=auth,
        pairing=PairingBroker(b"z" * 32, clock=lambda: 1_800_000_000),
    )


def test_catalog_has_no_raw_secret_tool():
    surface = make_surface()
    names = {tool["name"] for tool in surface.list_tools()}
    assert "get_password" not in names
    assert "get_token" not in names
    assert "wexspace_pairing_issue" in names


def test_device_list_is_secretless():
    result = make_surface().call("wexspace_devices_list", {})
    assert len(result["devices"]) == 2
    assert "token" not in str(result).lower()
    assert "password" not in str(result).lower()


def test_route_plan_exposes_native_openai_lane_for_pc():
    result = make_surface().call("wexspace_route_plan", {
        "controller_device_id": "phone-1",
        "target_device_id": "pc-1",
        "client_surface": "chatgpt_mobile",
    })
    assert result["route"]["lane"] == "openai_native_remote"


def test_pairing_issue_marks_payload_sensitive():
    result = make_surface().call("wexspace_pairing_issue", {
        "controller_device_id": "pc-1",
        "target_device_id": "phone-1",
        "requested_lane": ControlLane.WEXSPACE_ANDROID_MCP.value,
        "ttl_seconds": 60,
    })
    assert result["pairing_uri"].startswith("wexspace://pair/")
    assert result["sensitive"] is True


def test_authority_check_returns_ids_not_secrets():
    result = make_surface().call("wexspace_authority_check", {
        "provider": "google_drive",
        "principal": "owner",
        "mode": "write",
        "scope": "files.write",
        "device_id": "pc-1",
    })
    assert result == {
        "allowed": True,
        "matching_grant_ids": ["drive-main"],
        "raw_secret_exposed": False,
    }


def test_openai_probe_does_not_contact_provider():
    result = make_surface().call("wexspace_openai_remote_probe", {
        "payload": "openai-example://pair/opaque"
    })
    assert result["provider_contacted"] is False
    assert result["credential_interception"] is False
