from __future__ import annotations

import io
import os
import secrets

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import qrcode

from .core import PairingEnvelope, RendezvousStore


app = FastAPI(title="WEXSPACE Pairing Relay", version="0.1.0")
store = RendezvousStore()
_signing_key = os.environ.get("WEXSPACE_PAIRING_SIGNING_KEY")
if _signing_key:
    signing_key = _signing_key.encode("utf-8")
else:
    # Candidate/runtime-local fallback. Production MUST supply a stable secret.
    signing_key = secrets.token_bytes(32)
envelope = PairingEnvelope(signing_key)


class CreatePairing(BaseModel):
    ttl_seconds: int = Field(default=180, ge=30, le=600)


class ClaimPairing(BaseModel):
    code: str
    target_device_id: str
    public_key_fingerprint: str
    capabilities: list[str] = []


class ConfirmPairing(BaseModel):
    controller_nonce: str


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "wexspace-pairing-relay-r01"}


@app.post("/v1/pairings")
def create_pairing(payload: CreatePairing, request: Request) -> dict:
    session = store.create(ttl_seconds=payload.ttl_seconds)
    base_url = str(request.base_url).rstrip("/")
    pairing_url = envelope.encode(session, base_url)
    return {
        **store.public_view(session),
        "pairing_url": pairing_url,
        # Returned once to the controller; never included in public status.
        "controller_nonce": session.controller_nonce,
    }


@app.post("/v1/pairings/claim")
def claim_pairing(payload: ClaimPairing) -> dict:
    try:
        session = store.claim(
            code=payload.code,
            target_device_id=payload.target_device_id,
            public_key_fingerprint=payload.public_key_fingerprint,
            capabilities=payload.capabilities,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.public_view(session)


@app.get("/v1/pairings/{session_id}")
def pairing_status(session_id: str) -> dict:
    try:
        return store.public_view(store.get(session_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/pairings/{session_id}/confirm")
def confirm_pairing(session_id: str, payload: ConfirmPairing) -> dict:
    try:
        return store.public_view(
            store.confirm(session_id=session_id, controller_nonce=payload.controller_nonce)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/pairings/{session_id}/qr.png")
def pairing_qr(session_id: str, request: Request) -> Response:
    try:
        session = store.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pairing_url = envelope.encode(session, str(request.base_url).rstrip("/"))
    image = qrcode.make(pairing_url)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/remote", response_class=HTMLResponse)
def remote_page() -> str:
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WEXSPACE Remote</title>
<style>
body{font-family:system-ui;margin:0;background:#0b0d10;color:#f4f7fb}main{max-width:760px;margin:auto;padding:32px}
.card{background:#151920;border:1px solid #29313d;border-radius:22px;padding:24px;margin-top:24px}
button{font:inherit;padding:14px 18px;border-radius:14px;border:0;cursor:pointer}
#code{font-size:42px;letter-spacing:.2em;font-weight:700}img{max-width:260px;background:white;padding:12px;border-radius:16px}
small{color:#aab5c2}
</style></head>
<body><main><h1>WEXSPACE Remote</h1>
<p>Pair this browser with a WEXSPACE-enabled device. The code is short-lived and single-use.</p>
<button id="create">Create pairing</button>
<div class="card" id="card" hidden><div id="code"></div><p><img id="qr"></p>
<small id="status"></small></div>
<script>
let state=null;
async function create(){
 const r=await fetch('/v1/pairings',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});
 state=await r.json();
 document.querySelector('#code').textContent=state.code;
 document.querySelector('#qr').src='/v1/pairings/'+state.session_id+'/qr.png';
 document.querySelector('#card').hidden=false;
 poll();
}
async function poll(){
 if(!state)return;
 const r=await fetch('/v1/pairings/'+state.session_id,{cache:'no-store'});
 if(!r.ok)return;
 const s=await r.json();
 document.querySelector('#status').textContent='Status: '+s.state+' · expires '+new Date(s.expires_at*1000).toLocaleTimeString();
 if(s.state!=='PAIRED' && Date.now()/1000<s.expires_at)setTimeout(poll,1500);
}
document.querySelector('#create').onclick=create;
</script></main></body></html>"""
