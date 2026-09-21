# WEXSPACE Pairing Relay R01

Status: deployment-ready candidate, not canonical.

The relay provides a WEXSPACE-owned rendezvous layer for same-device or cross-device pairing:
browser/mobile/desktop -> short-lived code + QR -> WEXSPACE-enabled target device -> controller confirmation.

It does not transport raw passwords, cookies, OAuth tokens, bearer tokens, MFA seeds, recovery codes, or private keys.

Routes:
- GET /remote : lightweight browser pairing UI
- POST /v1/pairings : create one 30-600 second pairing session
- POST /v1/pairings/claim : device claims a numeric code with public-key fingerprint/capabilities
- GET /v1/pairings/{id} : status
- POST /v1/pairings/{id}/confirm : controller confirms using controller nonce
- GET /v1/pairings/{id}/qr.png : QR for the signed pairing URL
- GET /healthz : health

Current implementation uses an in-memory bounded store, appropriate for one-process qualification only. Before multi-instance production promotion, replace it with a shared TTL store and use a stable secret manager key via WEXSPACE_PAIRING_SIGNING_KEY.

The target device must still have a qualified native capability (for Android, AccessibilityService/MCP in the WEXSPACE app or companion module). A web page alone cannot provide Android system-wide UI control.
