from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .remote_fabric import (
    AuthorityRegistry,
    ControlLane,
    DeviceRegistry,
    GrantMode,
    OpenAINativeRemoteCompatibilityProbe,
    PairingBroker,
    RemoteRoutePlanner,
)


TOOL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "wexspace_devices_list",
        "description": "List owner-authorized devices registered in the WEXSPACE remote fabric.",
        "side_effect": "read",
        "requires_provider_confirmation": False,
    },
    {
        "name": "wexspace_route_plan",
        "description": "Choose the qualified control lane for a controller/target device pair.",
        "side_effect": "read",
        "requires_provider_confirmation": False,
    },
    {
        "name": "wexspace_pairing_issue",
        "description": "Issue a short-lived single-use WEXSPACE pairing link/QR payload.",
        "side_effect": "write",
        "requires_provider_confirmation": True,
    },
    {
        "name": "wexspace_authority_check",
        "description": "Check whether an opaque provider authority grant permits one requested operation.",
        "side_effect": "read",
        "requires_provider_confirmation": False,
    },
    {
        "name": "wexspace_openai_remote_probe",
        "description": "Fingerprint and structurally classify an owner-supplied OpenAI Remote pairing payload without contacting provider enrollment endpoints.",
        "side_effect": "read",
        "requires_provider_confirmation": False,
    },
)


class RemoteFabricAppSurface:
    """
    Provider-neutral application surface intended to be wrapped by MCP / Apps SDK.

    The core exposes no raw credential retrieval tool. Write-class operations are
    explicitly marked so ChatGPT/Gemini/provider policy can require confirmation.
    """

    def __init__(
        self,
        *,
        devices: DeviceRegistry,
        authorities: AuthorityRegistry,
        pairing: PairingBroker,
    ) -> None:
        self.devices = devices
        self.authorities = authorities
        self.pairing = pairing
        self.routes = RemoteRoutePlanner(devices)

    def list_tools(self) -> list[dict[str, Any]]:
        return [dict(tool) for tool in TOOL_CATALOG]

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "wexspace_devices_list":
            return {
                "devices": [
                    {
                        "device_id": d.device_id,
                        "kind": d.kind.value,
                        "display_name": d.display_name,
                        "online": d.online,
                        "capabilities": sorted(d.capabilities),
                        "provider_handles": list(d.provider_handles),
                    }
                    for d in self.devices.list()
                ]
            }

        if name == "wexspace_route_plan":
            route = self.routes.choose(
                controller_device_id=args["controller_device_id"],
                target_device_id=args["target_device_id"],
                client_surface=args["client_surface"],
            )
            return {
                "route": {
                    **asdict(route),
                    "lane": route.lane.value,
                }
            }

        if name == "wexspace_pairing_issue":
            ticket = self.pairing.issue(
                target_device_id=args["target_device_id"],
                controller_device_id=args["controller_device_id"],
                requested_lane=ControlLane(args["requested_lane"]),
                ttl_seconds=int(args.get("ttl_seconds", 120)),
            )
            return {
                "pairing_uri": ticket.uri,
                "expires_at": ticket.expires_at,
                "sensitive": True,
                "storage_rule": "Do not persist or log the pairing URI after handoff.",
            }

        if name == "wexspace_authority_check":
            grants = self.authorities.find(
                provider=args["provider"],
                principal=args["principal"],
                mode=GrantMode(args["mode"]),
                scope=args["scope"],
                device_id=args.get("device_id"),
            )
            return {
                "allowed": bool(grants),
                "matching_grant_ids": [g.grant_id for g in grants],
                "raw_secret_exposed": False,
            }

        if name == "wexspace_openai_remote_probe":
            obs = OpenAINativeRemoteCompatibilityProbe.observe_pairing_payload(args["payload"])
            return {
                "observation": asdict(obs),
                "provider_contacted": False,
                "credential_interception": False,
            }

        raise KeyError(f"unknown tool: {name}")
