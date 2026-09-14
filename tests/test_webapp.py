import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.webapp import make_server


@pytest.fixture
def demo_server(tmp_path):
    server = make_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(base, path, body=None, headers=None):
    raw = json.dumps(body).encode() if body is not None else None
    merged = {"Content-Type": "application/json"} if raw else {}
    merged.update(headers or {})
    with urlopen(Request(base + path, data=raw, headers=merged), timeout=5) as response:
        return json.load(response)


def test_demo_api_retries_preserve_cursor_effects_and_human_gate(demo_server):
    base, state = demo_server
    work_id = "DEMO-" + "0" * 32
    body = {"work_id": work_id, "label": "Synthetic retry qualification"}
    first = request(base, "/api/demo", body)
    assert first["work"]["cursor"] == 1
    before = GovernedRuntime(state).ledger.read_all()
    assert request(base, "/api/demo", body)["work"]["cursor"] == 1
    assert GovernedRuntime(state).ledger.read_all() == before
    with pytest.raises(HTTPError) as not_ready:
        request(base, "/api/receipt/" + work_id)
    assert not_ready.value.code == 409
    assert request(base, "/api/resume/" + work_id, {})["work"]["state"] == "HUMAN_REVIEW"
    before = GovernedRuntime(state).ledger.read_all()
    request(base, "/api/resume/" + work_id, {})
    assert GovernedRuntime(state).ledger.read_all() == before
    receipt = request(base, "/api/receipt/" + work_id)
    assert receipt["effect_counts"] == {"inspect_request": 1, "reconcile_evidence": 1, "prepare_review_package": 1}
    assert receipt["decision"]["agent_may_auto_approve"] is False
    assert receipt["decision"]["reconciliation"]["delta"] == -2
    assert receipt["evidence_chain_valid"]
    assert receipt["model_inference"] is False


@pytest.mark.parametrize("headers", [{"Origin": "https://untrusted.example"}, {"Host": "untrusted.example"}])
def test_cross_origin_or_rebound_host_cannot_create_work(demo_server, headers):
    base, _ = demo_server
    with pytest.raises(HTTPError) as denied:
        request(base, "/api/demo", {"work_id": "DEMO-" + "1" * 32, "label": "Synthetic"}, headers)
    assert denied.value.code == 403


def test_no_agent_approval_endpoint(demo_server):
    base, _ = demo_server
    with pytest.raises(HTTPError) as absent:
        request(base, "/api/approve", {})
    assert absent.value.code == 404
