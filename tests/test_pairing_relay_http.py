from __future__ import annotations

from fastapi.testclient import TestClient

from services.pairing_relay.app import app


client = TestClient(app)


def test_health():
    r=client.get("/healthz")
    assert r.status_code==200
    assert r.json()["status"]=="ok"


def test_browser_pairing_create_and_qr():
    r=client.post("/v1/pairings",json={})
    assert r.status_code==200
    body=r.json()
    assert len(body["code"])==6
    assert body["pairing_url"].startswith("http://testserver/pair/")
    q=client.get(f"/v1/pairings/{body['session_id']}/qr.png")
    assert q.status_code==200
    assert q.headers["content-type"].startswith("image/png")


def test_signed_pairing_landing():
    body=client.post("/v1/pairings",json={"ttl_seconds":60}).json()
    path=body["pairing_url"].replace("http://testserver","")
    r=client.get(path)
    assert r.status_code==200
    assert body["code"] in r.text
    assert "Open WEXSPACE" in r.text


def test_mcp_initialize_and_tools_list():
    r=client.post("/mcp",json={
        "jsonrpc":"2.0","id":1,"method":"initialize",
        "params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1"}}
    })
    assert r.status_code==200
    assert r.json()["result"]["serverInfo"]["name"]=="wexspace-pairing-relay"
    t=client.post("/mcp",json={"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
    names={x["name"] for x in t.json()["result"]["tools"]}
    assert names=={"wexspace_pairing_create","wexspace_pairing_status"}


def test_mcp_create_does_not_return_controller_nonce():
    r=client.post("/mcp",json={
        "jsonrpc":"2.0","id":3,"method":"tools/call",
        "params":{"name":"wexspace_pairing_create","arguments":{"ttl_seconds":60}}
    })
    assert r.status_code==200
    result=r.json()["result"]["structuredContent"]
    assert len(result["code"])==6
    assert "controller_nonce" not in result
