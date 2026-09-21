from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable
from urllib.parse import urlparse


class DeviceKind(str, Enum):
    ANDROID = "android"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


class ControlLane(str, Enum):
    OPENAI_NATIVE_REMOTE = "openai_native_remote"
    WEXSPACE_ANDROID_MCP = "wexspace_android_mcp"
    WEXSPACE_PAIRING = "wexspace_pairing"
    GEMINI_CUSTOM_MCP = "gemini_custom_mcp"
    CHATGPT_APP_SURFACE = "chatgpt_app_surface"


class GrantMode(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass(frozen=True)
class DeviceEndpoint:
    device_id: str
    kind: DeviceKind
    display_name: str
    owner_principal: str
    online: bool = False
    capabilities: frozenset[str] = field(default_factory=frozenset)
    provider_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorityGrant:
    grant_id: str
    provider: str
    principal: str
    modes: frozenset[GrantMode]
    scopes: frozenset[str]
    opaque_authority_handle: str
    device_ids: frozenset[str] = field(default_factory=frozenset)

    def allows(self, *, mode: GrantMode, scope: str, device_id: str | None = None) -> bool:
        if mode not in self.modes:
            return False
        if scope not in self.scopes:
            return False
        if device_id is not None and self.device_ids and device_id not in self.device_ids:
            return False
        return True


@dataclass(frozen=True)
class PairingTicket:
    token: str
    expires_at: int
    target_device_id: str
    controller_device_id: str
    requested_lane: ControlLane

    @property
    def uri(self) -> str:
        return f"wexspace://pair/{self.token}"


@dataclass(frozen=True)
class RouteDecision:
    controller_device_id: str
    target_device_id: str
    lane: ControlLane
    reason: str
    provider_native_confirmation_may_be_required: bool = False


@dataclass(frozen=True)
class OpenAIRemoteObservation:
    fingerprint_sha256: str
    payload_kind: str
    scheme: str | None
    host: str | None
    path: str | None
    byte_length: int


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, DeviceEndpoint] = {}

    def upsert(self, device: DeviceEndpoint) -> None:
        self._devices[device.device_id] = device

    def get(self, device_id: str) -> DeviceEndpoint:
        try:
            return self._devices[device_id]
        except KeyError as exc:
            raise KeyError(f"unknown device: {device_id}") from exc

    def list(self) -> list[DeviceEndpoint]:
        return sorted(self._devices.values(), key=lambda d: d.device_id)


class AuthorityRegistry:
    """
    Stores only opaque authority handles and policy metadata.
    Raw passwords, cookies, access tokens, refresh tokens, API keys,
    MFA seeds, and recovery codes must remain outside model-readable state.
    """

    def __init__(self) -> None:
        self._grants: dict[str, AuthorityGrant] = {}

    def upsert(self, grant: AuthorityGrant) -> None:
        if not grant.opaque_authority_handle or grant.opaque_authority_handle.isspace():
            raise ValueError("opaque_authority_handle is required")
        self._grants[grant.grant_id] = grant

    def find(
        self,
        *,
        provider: str,
        principal: str,
        mode: GrantMode,
        scope: str,
        device_id: str | None = None,
    ) -> list[AuthorityGrant]:
        return [
            g
            for g in self._grants.values()
            if g.provider == provider
            and g.principal == principal
            and g.allows(mode=mode, scope=scope, device_id=device_id)
        ]


class PairingBroker:
    """
    WEXSPACE pairing is deliberately separate from proprietary provider QR
    protocols. The QR/link carries only a short-lived signed ticket. It never
    carries a long-lived password, OAuth token, bearer token, or private key.
    """

    def __init__(self, signing_key: bytes, *, clock=time.time) -> None:
        if len(signing_key) < 32:
            raise ValueError("signing_key must be at least 32 bytes")
        self._signing_key = signing_key
        self._clock = clock
        self._consumed: set[str] = set()

    @classmethod
    def generate(cls) -> "PairingBroker":
        return cls(secrets.token_bytes(32))

    def issue(
        self,
        *,
        target_device_id: str,
        controller_device_id: str,
        requested_lane: ControlLane,
        ttl_seconds: int = 120,
    ) -> PairingTicket:
        if ttl_seconds < 15 or ttl_seconds > 600:
            raise ValueError("ttl_seconds must be between 15 and 600")
        now = int(self._clock())
        payload = {
            "v": 1,
            "jti": secrets.token_urlsafe(12),
            "target": target_device_id,
            "controller": controller_device_id,
            "lane": requested_lane.value,
            "iat": now,
            "exp": now + ttl_seconds,
        }
        body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        sig = _b64url(hmac.new(self._signing_key, body.encode(), hashlib.sha256).digest())
        token = f"{body}.{sig}"
        return PairingTicket(
            token=token,
            expires_at=payload["exp"],
            target_device_id=target_device_id,
            controller_device_id=controller_device_id,
            requested_lane=requested_lane,
        )

    def verify_and_consume(self, token: str) -> dict:
        if token in self._consumed:
            raise ValueError("pairing ticket already consumed")
        try:
            body, sig = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("invalid pairing token") from exc
        expected = _b64url(hmac.new(self._signing_key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("invalid pairing signature")
        try:
            payload = json.loads(_b64urldecode(body))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("invalid pairing payload") from exc
        now = int(self._clock())
        if payload.get("exp", 0) < now:
            raise ValueError("pairing ticket expired")
        if payload.get("iat", 0) > now + 5:
            raise ValueError("pairing ticket issued in the future")
        self._consumed.add(token)
        return payload


class RemoteRoutePlanner:
    """
    Deterministic routing across OpenAI-native desktop Remote, Android MCP,
    Gemini custom MCP, ChatGPT app surfaces, and WEXSPACE-owned pairing.
    """

    def __init__(self, devices: DeviceRegistry) -> None:
        self.devices = devices

    def choose(
        self,
        *,
        controller_device_id: str,
        target_device_id: str,
        client_surface: str,
    ) -> RouteDecision:
        controller = self.devices.get(controller_device_id)
        target = self.devices.get(target_device_id)
        if not target.online:
            raise ValueError("target device is offline")

        surface = client_surface.lower().strip()

        if target.kind in {DeviceKind.WINDOWS, DeviceKind.MACOS} and "openai_remote_host" in target.capabilities:
            if surface in {"chatgpt_mobile", "codex_desktop", "chatgpt_desktop"}:
                return RouteDecision(
                    controller_device_id,
                    target_device_id,
                    ControlLane.OPENAI_NATIVE_REMOTE,
                    "Supported OpenAI-native host/control surface available.",
                    provider_native_confirmation_may_be_required=True,
                )

        if target.kind == DeviceKind.ANDROID and "mcp_server" in target.capabilities:
            if surface in {"gemini_spark", "gemini_web"}:
                return RouteDecision(
                    controller_device_id,
                    target_device_id,
                    ControlLane.GEMINI_CUSTOM_MCP,
                    "Android host exposes MCP and Gemini custom-MCP surface is selected.",
                    provider_native_confirmation_may_be_required=True,
                )
            return RouteDecision(
                controller_device_id,
                target_device_id,
                ControlLane.WEXSPACE_ANDROID_MCP,
                "Android host control uses WEXSPACE MCP relay.",
                provider_native_confirmation_may_be_required=True,
            )

        if "wexspace_pairing" in target.capabilities:
            return RouteDecision(
                controller_device_id,
                target_device_id,
                ControlLane.WEXSPACE_PAIRING,
                "Provider-native route unavailable; use WEXSPACE short-lived pairing.",
                provider_native_confirmation_may_be_required=True,
            )

        raise ValueError(
            f"no qualified route from {controller.kind.value} to {target.kind.value} on {client_surface}"
        )


class OpenAINativeRemoteCompatibilityProbe:
    """
    Black-box compatibility probe for owner-authorized experiments.

    This intentionally does NOT:
    - capture provider credentials/tokens;
    - bypass account/workspace checks;
    - call undocumented OpenAI enrollment endpoints;
    - impersonate a host identity.

    It can safely fingerprint and structurally classify a pairing payload the
    owner explicitly supplies (for example, decoded from a QR generated on an
    owner-controlled machine). This lets WEXSPACE compare observations across
    supported hosts while keeping proprietary protocol assumptions quarantined.
    """

    @staticmethod
    def observe_pairing_payload(payload: str) -> OpenAIRemoteObservation:
        raw = payload.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        parsed = urlparse(payload)
        if parsed.scheme and (parsed.netloc or parsed.path):
            return OpenAIRemoteObservation(
                fingerprint_sha256=digest,
                payload_kind="uri",
                scheme=parsed.scheme,
                host=parsed.hostname,
                path=parsed.path or None,
                byte_length=len(raw),
            )
        return OpenAIRemoteObservation(
            fingerprint_sha256=digest,
            payload_kind="opaque",
            scheme=None,
            host=None,
            path=None,
            byte_length=len(raw),
        )


def sanitize_capabilities(values: Iterable[str]) -> frozenset[str]:
    cleaned = []
    for value in values:
        v = value.strip().lower()
        if not v:
            continue
        if any(secretish in v for secretish in ("password=", "token=", "cookie=", "secret=")):
            raise ValueError("capabilities must not contain secret material")
        cleaned.append(v)
    return frozenset(cleaned)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64urldecode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("ascii"))
