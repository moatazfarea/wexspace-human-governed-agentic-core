"""Loopback-only synthetic judge demo. This is not a multi-user cloud server."""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
from typing import Any

from .runtime import GovernedRuntime
from .state import NODE_ORDER

INPUTS = {"request_id": "SYNTHETIC-001", "expected_quantity": 120, "observed_quantity": 118}
ID_PATTERN = re.compile(r"DEMO-[a-f0-9]{32}\Z")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WEXSPACE · Governed work</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;color:#e8eef7;background:#0b1220}
*{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:auto;padding:32px}
header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #28364b;padding-bottom:20px}
.brand{letter-spacing:.15em;font-weight:750}.tag{font-size:13px;color:#9edac9;background:#12372f;padding:8px 12px;border-radius:20px}
h1{font-size:40px;letter-spacing:-.04em;margin:28px 0 10px}p{color:#acbbcf;line-height:1.6}
.layout{display:grid;grid-template-columns:1.1fr 1fr;gap:24px;margin-top:24px}
.panel{background:#121e30;border:1px solid #28364b;border-radius:16px;padding:24px}
label{display:block;margin:12px 0;color:#c4d1e0}input{font:inherit;width:100%;color:inherit;background:#0b1220;border:1px solid #3e526d;padding:12px;border-radius:8px}
button,a.button{font:inherit;border:0;border-radius:8px;padding:12px 16px;background:#83e0bd;color:#09261d;font-weight:650;cursor:pointer;margin:8px 6px 8px 0}
button.secondary{background:#283a53;color:#e8eef7}button:disabled{opacity:.4;cursor:default}
button:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid #ffce75;outline-offset:3px}
.metrics{display:flex;gap:24px;margin:20px 0}.metrics strong{display:block;font-size:30px}.metrics span{color:#acbbcf;font-size:13px}
ol{padding:0;list-style:none}li{padding:16px 0;border-bottom:1px solid #28364b;display:flex;justify-content:space-between}
li b{font-weight:550}li span{color:#acbbcf}.pass{color:#83e0bd!important}
#status{min-height:48px;color:#ffce75}#cursor{font-family:ui-monospace,monospace}
pre{font-size:12px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1220;padding:16px;border-radius:10px}
small{color:#91a2bb}a{color:#83e0bd}footer{padding:28px 0;color:#91a2bb;font-size:13px}
@media(max-width:760px){.layout{grid-template-columns:1fr}main{padding:18px}h1{font-size:30px}}
</style><script src="/app.js" defer></script></head><body><main>
<header><div class="brand">WEXSPACE AI</div><div class="tag">Synthetic workflow · deterministic tools</div></header>
<h1>Work continues. Authority stays human.</h1>
<p>Inspect a receiving discrepancy, preserve the evidence, and resume the same work after interruption.</p>
<div class="layout"><section class="panel"><h2>Receiving review</h2>
<label for="label">Case label</label><input id="label" maxlength="80" value="Synthetic receiving variance">
<div class="metrics"><div><strong>120</strong><span>Expected units</span></div><div><strong>118</strong><span>Received units</span></div><div><strong>−2</strong><span>Input variance</span></div></div>
<button id="start">Start synthetic case</button><button id="refresh" class="secondary">Reconnect to saved work</button>
<p id="status" role="status" aria-live="polite">Ready to inspect synthetic evidence.</p>
<small id="work">No work started</small>
<ol><li><b>1 · Inspect request</b><span id="inspect_request">PENDING</span></li>
<li><b>2 · Reconcile evidence</b><span id="reconcile_evidence">PENDING</span></li>
<li><b>3 · Prepare review package</b><span id="prepare_review_package">PENDING</span></li></ol>
<div id="cursor">Durable cursor: — / 3</div><button id="resume" disabled>Resume safe work</button>
</section><section class="panel"><h2>Evidence receipt</h2>
<p>Results come from this running Python service and its SQLite state. The agent has no decision-approval endpoint.</p>
<button id="receipt" class="secondary" disabled>Read evidence receipt</button>
<pre id="evidence">The receipt becomes available at HUMAN_REVIEW.</pre>
<p><strong>Human decision boundary</strong><br><small>Review is required. No consequential decision is finalized by this demo.</small></p>
</section></div>
<footer>Local judge demo · No cloud model invocation in this mode ·
<a href="https://github.com/moatazfarea/wexspace-human-governed-agentic-core">Public source and qualification</a></footer>
</main></body></html>
"""

JAVASCRIPT = """
const $ = id => document.getElementById(id);
const nodes = ['inspect_request','reconcile_evidence','prepare_review_package'];
let workId = sessionStorage.getItem('wexspace-demo-work') || '';
async function api(path, body) {
  const options = body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  const response = await fetch(path,options);
  if (!response.ok) throw new Error('Request failed ('+response.status+'). Saved work is preserved.');
  return await response.json();
}
function render(data) {
  $('work').textContent = data.work.id;
  $('cursor').textContent = 'Durable cursor: '+data.work.cursor+' / 3';
  for (const name of nodes) {
    $(name).textContent = data.nodes[name].state;
    $(name).className = data.nodes[name].state === 'PASS' ? 'pass' : '';
  }
  const review = data.work.state === 'HUMAN_REVIEW';
  $('status').textContent = review ? 'HUMAN_REVIEW — evidence ready; decision remains with a person.' : 'Inspection saved. Resume continues from the durable cursor.';
  $('resume').disabled = review;
  $('receipt').disabled = !review;
}
async function guarded(fn) {
  for (const id of ['start','refresh','resume','receipt']) $(id).disabled = true;
  try { await fn(); } catch (error) {
    $('status').textContent = 'Service unavailable. Saved work stays on disk. Reconnect when the service returns.';
  } finally {
    $('start').disabled = false;
    $('refresh').disabled = false;
  }
}
$('start').onclick = () => guarded(async () => {
  workId = 'DEMO-'+crypto.randomUUID().replaceAll('-','');
  sessionStorage.setItem('wexspace-demo-work', workId);
  render(await api('/api/demo',{work_id:workId,label:$('label').value}));
});
$('refresh').onclick = () => guarded(async () => {
  if (!workId) { $('status').textContent = 'Start a synthetic case first.'; return; }
  render(await api('/api/status/'+workId));
});
$('resume').onclick = () => guarded(async () => render(await api('/api/resume/'+workId,{})));
$('receipt').onclick = () => guarded(async () => {
  const receipt = await api('/api/receipt/'+workId);
  $('evidence').textContent = JSON.stringify(receipt,null,2);
  render(await api('/api/status/'+workId));
});
if (workId) $('refresh').click();
"""


def make_server(state_dir: Path, port: int = 8080) -> HTTPServer:
    runtime = GovernedRuntime(state_dir)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def valid_host(self) -> bool:
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def respond(self, code: int, data: Any, content_type: str = "application/json") -> None:
            raw = (json.dumps(data, sort_keys=True) if content_type == "application/json" else data).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def status(self, work_id: str) -> dict[str, Any]:
            if not ID_PATTERN.fullmatch(work_id):
                raise ValueError("Invalid synthetic work ID")
            return runtime.status(work_id)

        def do_GET(self) -> None:
            if not self.valid_host():
                self.respond(403, {"error": "Loopback host required"})
                return
            try:
                if self.path == "/":
                    self.respond(200, PAGE, "text/html")
                elif self.path == "/app.js":
                    self.respond(200, JAVASCRIPT, "text/javascript")
                elif self.path.startswith("/api/status/"):
                    self.respond(200, self.status(self.path.removeprefix("/api/status/")))
                elif self.path.startswith("/api/receipt/"):
                    work_id = self.path.removeprefix("/api/receipt/")
                    status = self.status(work_id)
                    if status["work"]["state"] != "HUMAN_REVIEW":
                        self.respond(409, {"error": "Human review package is not ready"})
                        return
                    decision = status["nodes"]["prepare_review_package"]["output"]
                    digest = hashlib.sha256(json.dumps(decision, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                    self.respond(200, {
                        "work_id": work_id, "cursor": status["work"]["cursor"],
                        "state": "HUMAN_REVIEW", "model_inference": False,
                        "decision": decision, "decision_sha256": digest,
                        "evidence_chain_valid": status["evidence_valid"],
                        "effect_counts": {node: runtime.repo.effect_count(work_id, f"tool:{node}") for node in NODE_ORDER},
                        "scope": "Local synthetic deterministic workflow; hashes provide integrity, not third-party attestation.",
                    })
                else:
                    self.respond(404, {"error": "Not found"})
            except (KeyError, ValueError):
                self.respond(404, {"error": "Synthetic work not found"})

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            expected_origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if not self.valid_host() or (origin is not None and origin not in expected_origins) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.respond(403, {"error": "Same-origin loopback request required"})
                return
            if self.headers.get("Content-Type") != "application/json":
                self.respond(415, {"error": "JSON required"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2048:
                    raise ValueError("Invalid body size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Object required")
                if self.path == "/api/demo":
                    work_id, label = body.get("work_id", ""), body.get("label", "")
                    if not isinstance(work_id, str) or not ID_PATTERN.fullmatch(work_id):
                        raise ValueError("Invalid work ID")
                    if not isinstance(label, str) or not 1 <= len(label) <= 80:
                        raise ValueError("Invalid synthetic label")
                    try:
                        runtime.repo.work(work_id)
                    except KeyError:
                        runtime.create_work(work_id, label, INPUTS)
                        runtime.run_deterministic(work_id, stop_after=1)
                    self.respond(200, self.status(work_id))
                elif self.path.startswith("/api/resume/"):
                    work_id = self.path.removeprefix("/api/resume/")
                    self.status(work_id)
                    runtime.run_deterministic(work_id)
                    self.respond(200, self.status(work_id))
                else:
                    self.respond(404, {"error": "Not found"})
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                self.respond(400, {"error": "Invalid synthetic request"})

    return HTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path(".wexspace-demo"))
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = make_server(args.state_dir, args.port)
    print(json.dumps({"event": "ready", "port": server.server_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
