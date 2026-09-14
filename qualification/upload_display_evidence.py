"""Persist reviewed synthetic display evidence to a separate public Git branch."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

root = Path("display-evidence")
if not (root / "manifest.json").exists():
    print("No recording was started; no evidence upload.")
    raise SystemExit(0)
token = os.environ["GITHUB_TOKEN"]
repo = os.environ["GITHUB_REPOSITORY"]
source = os.environ["GITHUB_SHA"]
run_id = os.environ["GITHUB_RUN_ID"]
attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
assert re.fullmatch(r"[0-9]+", run_id) and re.fullmatch(r"[0-9]+", attempt)
branch = "afh-display-evidence-20260914"
prefix = f"evidence/display/{run_id}-{attempt}"
api_base = f"https://api.github.com/repos/{repo}/"


def api(path, data=None, method=None, allow_missing=False):
    raw = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(api_base + path, data=raw, method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise RuntimeError(f"GitHub evidence API returned HTTP {error.code}") from None


ref = api(f"git/ref/heads/{branch}", allow_missing=True)
parent = ref["object"]["sha"] if ref else source
current = api(f"contents/{prefix}/manifest.json?ref={branch}", allow_missing=True) if ref else None
if current:
    if base64.b64decode(current["content"]) == (root / "manifest.json").read_bytes():
        print("Evidence already persisted; duplicate upload skipped.")
        raise SystemExit(0)
    raise RuntimeError("Existing recording evidence differs; refusing to overwrite.")

tree = api(f"git/commits/{parent}")["tree"]["sha"]
entries = []
total = 0
for name in ["segment.mp4", "preview.png", "receipt.json", "manifest.json"]:
    path = root / name
    if not path.exists():
        continue
    data = path.read_bytes()
    total += len(data)
    if len(data) > 8_000_000 or total > 12_000_000:
        raise RuntimeError("Bounded evidence size exceeded")
    blob = api("git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
    entries.append({"path": f"{prefix}/{name}", "mode": "100644", "type": "blob", "sha": blob["sha"]})
new_tree = api("git/trees", {"base_tree": tree, "tree": entries})["sha"]
commit = api("git/commits", {"message": f"evidence: preserve actual display segment for run {run_id}",
                            "tree": new_tree, "parents": [parent]})["sha"]
if ref:
    api(f"git/refs/heads/{branch}", {"sha": commit, "force": False}, "PATCH")
else:
    api("git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
readback = api(f"git/ref/heads/{branch}")
assert readback["object"]["sha"] == commit
remote = api(f"contents/{prefix}/manifest.json?ref={commit}")
assert base64.b64decode(remote["content"]) == (root / "manifest.json").read_bytes()
print(json.dumps({"state": "DIRECTLY_VERIFIED", "evidence_commit": commit,
    "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
    "url": f"https://github.com/{repo}/tree/{commit}/{prefix}",
    "source_commit": source, "uploaded_bytes": total}))
