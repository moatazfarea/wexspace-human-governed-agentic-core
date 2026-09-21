from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass
class PairingSession:
    session_id: str
    code: str
    controller_nonce: str
    created_at: int
    expires_at: int
    target_device_id: str | None = None
    target_public_key_fingerprint: str | None = None
    target_capabilities: tuple[str, ...] = ()
    state: str = "WAITING_FOR_DEVICE"
    consumed: bool = False


class RendezvousStore:
    """
    Thread-safe, bounded in-memory store for the R01 relay candidate.

    Production deployment must replace this with a durable/TTL-aware shared store
    before horizontal scaling. The API deliberately contains no account passwords,
    cookies, OAuth access/refresh tokens, bearer tokens, MFA seeds, or recovery codes.
    """

    def __init__(self, *, max_sessions: int = 500, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._max_sessions = max_sessions
        self._by_id: dict[str, PairingSession] = {}
        self._by_code: dict[str, str] = {}
        self._lock = threading.RLock()

    def create(self, *, ttl_seconds: int = 180) -> PairingSession:
        if ttl_seconds < 30 or ttl_seconds > 600:
            raise ValueError("ttl_seconds must be between 30 and 600")
        with self._lock:
            self._gc()
            if len(self._by_id) >= self._max_sessions:
                raise RuntimeError("pairing capacity reached")
            now = int(self._clock())
            session_id = "pair_" + secrets.token_urlsafe(16)
            code = self._unique_code()
            session = PairingSession(
                session_id=session_id,
                code=code,
                controller_nonce=secrets.token_urlsafe(24),
                created_at=now,
                expires_at=now + ttl_seconds,
            )
            self._by_id[session_id] = session
            self._by_code[code] = session_id
            return session

    def claim(
        self,
        *,
        code: str,
        target_device_id: str,
        public_key_fingerprint: str,
        capabilities: list[str],
    ) -> PairingSession:
        with self._lock:
            self._gc()
            session_id = self._by_code.get(self._normalize_code(code))
            if not session_id:
                raise KeyError("PAIRING_CODE_INVALID_OR_EXPIRED")
            session = self._by_id[session_id]
            if session.consumed or session.state != "WAITING_FOR_DEVICE":
                raise ValueError("PAIRING_SESSION_NOT_CLAIMABLE")
            if not target_device_id or not public_key_fingerprint:
                raise ValueError("DEVICE_ID_AND_PUBLIC_KEY_FINGERPRINT_REQUIRED")
            session.target_device_id = target_device_id[:128]
            session.target_public_key_fingerprint = public_key_fingerprint[:256]
            session.target_capabilities = tuple(sorted({c.strip().lower() for c in capabilities if c.strip()}))
            session.state = "DEVICE_CLAIMED"
            return session

    def confirm(self, *, session_id: str, controller_nonce: str) -> PairingSession:
        with self._lock:
            self._gc()
            session = self._by_id.get(session_id)
            if not session:
                raise KeyError("PAIRING_SESSION_INVALID_OR_EXPIRED")
            if session.state != "DEVICE_CLAIMED":
                raise ValueError("PAIRING_SESSION_NOT_READY")
            if not hmac.compare_digest(session.controller_nonce, controller_nonce):
                raise PermissionError("CONTROLLER_NONCE_INVALID")
            session.state = "PAIRED"
            session.consumed = True
            self._by_code.pop(session.code, None)
            return session

    def get(self, session_id: str) -> PairingSession:
        with self._lock:
            self._gc()
            session = self._by_id.get(session_id)
            if not session:
                raise KeyError("PAIRING_SESSION_INVALID_OR_EXPIRED")
            return session

    def public_view(self, session: PairingSession) -> dict:
        return {
            "session_id": session.session_id,
            "code": session.code,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "target_device_id": session.target_device_id,
            "target_public_key_fingerprint": session.target_public_key_fingerprint,
            "target_capabilities": list(session.target_capabilities),
            "state": session.state,
            "consumed": session.consumed,
        }

    def _unique_code(self) -> str:
        for _ in range(20):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if code not in self._by_code:
                return code
        raise RuntimeError("unable to allocate pairing code")

    @staticmethod
    def _normalize_code(code: str) -> str:
        return "".join(ch for ch in code if ch.isdigit())

    def _gc(self) -> None:
        now = int(self._clock())
        expired = [sid for sid, s in self._by_id.items() if s.expires_at < now]
        for sid in expired:
            session = self._by_id.pop(sid)
            self._by_code.pop(session.code, None)


class PairingEnvelope:
    """Signed QR/link payload; no long-lived credential material."""

    def __init__(self, signing_key: bytes, *, clock: Callable[[], float] = time.time):
        if len(signing_key) < 32:
            raise ValueError("signing key must be at least 32 bytes")
        self._key = signing_key
        self._clock = clock

    def encode(self, session: PairingSession, base_url: str) -> str:
        payload = {
            "v": 1,
            "sid": session.session_id,
            "code": session.code,
            "exp": session.expires_at,
            "aud": "wexspace-device-pairing",
        }
        body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        sig = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        return f"{base_url.rstrip('/')}/pair/{body}.{sig}"

    def decode_and_verify(self, token: str) -> dict:
        try:
            body, sig = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("PAIRING_ENVELOPE_INVALID") from exc
        expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("PAIRING_ENVELOPE_SIGNATURE_INVALID")
        pad = "=" * ((4 - len(body) % 4) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode((body + pad).encode("ascii")))
        except Exception as exc:
            raise ValueError("PAIRING_ENVELOPE_INVALID") from exc
        if payload.get("aud") != "wexspace-device-pairing" or payload.get("v") != 1:
            raise ValueError("PAIRING_ENVELOPE_INVALID")
        if int(payload.get("exp", 0)) < int(self._clock()):
            raise ValueError("PAIRING_ENVELOPE_EXPIRED")
        return payload
