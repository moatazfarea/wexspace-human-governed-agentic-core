# WEXSPACE Unified Remote Fabric R01

Status: ISOLATED_CANDIDATE — NOT CANONICAL

## Objective

Provide one governed multi-device control fabric spanning:

1. **OPENAI_NATIVE_DESKTOP_LANE** — use OpenAI's supported Remote capability for Mac/Windows hosts.
2. **WEXSPACE_ANDROID_DEVICE_LANE** — control an owner-authorized Android device through the Android Remote Control MCP relay.
3. **WEXSPACE_PAIRING_LAYER** — provider-neutral QR/link pairing with short-lived signed tickets, no long-lived secrets in the QR.
4. **GEMINI_CUSTOM_MCP_LANE** — Gemini Spark connects to the Android MCP endpoint via OAuth/DCR.
5. **CHATGPT_APP_SURFACE** — future Apps SDK/MCP presentation surface, subject to the product's supported capabilities and plan/workspace policy.
6. **AUTHORITY_REGISTRY** — stores only opaque authority handles and least-privilege metadata.

## Multi-device model

The registry supports any number of devices. A route is selected per controller/target pair, not globally.

Examples:

- Android phone -> Windows PC: OpenAI-native Remote when the PC is an enrolled supported host.
- Android phone -> Mac: OpenAI-native Remote when enrolled.
- Spark/Gemini -> Android phone: Gemini Custom MCP -> Android MCP.
- WEXSPACE client -> Android phone: Android MCP.
- WEXSPACE client -> desktop without provider-native route: WEXSPACE pairing adapter, when a host runtime is installed.
- One device may be both a controller and a target in different sessions, but loopback/self-control must be explicitly qualified.

## OpenAI native protocol experiment

The current implementation intentionally starts as a **black-box compatibility probe**, not a bypass.

Allowed experiment:
- Owner enables Remote on an owner-controlled supported Mac/Windows host.
- Owner supplies the QR-decoded payload or pairing artifact from that host.
- WEXSPACE fingerprints and structurally classifies the payload.
- Repeated observations may be compared for TTL/nonce/schema behavior.
- No raw auth token is written to evidence.

Not allowed in this candidate:
- intercepting credentials or TLS;
- replaying another user's pairing data;
- bypassing same-account/workspace enrollment;
- calling undocumented enrollment endpoints with fabricated identities;
- claiming Android is a supported OpenAI Remote host without live proof.

If OpenAI later publishes a host API/SDK, the compatibility probe can be replaced by a supported adapter.

## WEXSPACE pairing design

The QR/link contains a short-lived HMAC-signed ticket only:
- version;
- one-time ticket id;
- controller id;
- target id;
- requested lane;
- issued-at;
- expiry;
- signature.

Ticket lifetime is bounded to 15–600 seconds and single-use. It contains no password, OAuth token, bearer token, cookie, private key, MFA seed, or recovery code.

## Authority design

Provider data access is represented by an `AuthorityGrant` containing:
- provider;
- principal;
- allowed modes (read/write/admin);
- scopes;
- optional device allowlist;
- opaque authority handle.

Raw credentials remain in provider-native auth, OS credential manager, secret manager, passkey store, or other protected out-of-band authority source.

## Android OAuth compatibility

The current Android MCP candidate includes the separately qualified Gemini redirect allowlist patch. That build passed focused OAuth tests and APK build in GitHub Actions. Live install/pairing remains a separate gate.

## Security / policy boundary

OpenAI-native Remote stays provider-native. WEXSPACE does not spoof provider identity.

A reverse-engineering experiment may inspect owner-supplied pairing artifacts and public client behavior, but it must not weaken authentication or access controls.

For Android distribution, Google Play eligibility is a separate qualification. A full autonomous AccessibilityService controller must not be represented as Play-policy compliant until provider review/policy qualification proves it.

## Next live gates

1. Install the already-built Android MCP Gemini-OAuth candidate on the owner's test phone.
2. Rotate previously exposed bearer credentials.
3. Prove Gemini OAuth/DCR live.
4. Prove screen-read -> one reversible tap -> STOP/revoke -> reconnect.
5. Pair ChatGPT Remote with an owner-controlled supported Windows/Mac host using the official path and record a provider-native receipt.
6. If the owner chooses the OpenAI protocol experiment, capture only the QR payload/format from the owner's host and feed it to the black-box probe.
7. Build the WEXSPACE companion pairing UI after both provider-native and Android lanes have live receipts.
