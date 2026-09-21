#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from wexspace_human_governed_core.remote_fabric import OpenAINativeRemoteCompatibilityProbe


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fingerprint an owner-supplied OpenAI Remote pairing payload without "
            "contacting OpenAI or persisting the payload."
        )
    )
    parser.add_argument(
        "--payload",
        help="Pairing payload. Prefer stdin to avoid shell history.",
    )
    args = parser.parse_args()
    payload = args.payload
    if payload is None:
        payload = sys.stdin.read().strip()
    if not payload:
        parser.error("pairing payload is required")
    obs = OpenAINativeRemoteCompatibilityProbe.observe_pairing_payload(payload)
    print(json.dumps({
        "fingerprint_sha256": obs.fingerprint_sha256,
        "payload_kind": obs.payload_kind,
        "scheme": obs.scheme,
        "host": obs.host,
        "path": obs.path,
        "byte_length": obs.byte_length,
        "provider_contacted": False,
        "payload_persisted": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
