from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class EvidenceLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> str:
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record = {"sha256": digest, "event": event}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return digest

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def verify(self) -> bool:
        for record in self.read_all():
            canonical = json.dumps(record["event"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if digest != record["sha256"]:
                return False
        return True
