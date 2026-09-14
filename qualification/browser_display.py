"""Record an actual X11 display while testing the real loopback demo."""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


OUT = Path("display-evidence")
OUT.mkdir(exist_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def start_server(state, port=0):
    process = subprocess.Popen(
        [sys.executable, "-m", "wexspace_human_governed_core.webapp", "--state-dir", str(state), "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    ready = json.loads(process.stdout.readline())
    assert ready["event"] == "ready"
    return process, ready["port"]


def move_native_mouse(page, selector):
    box = page.locator(selector).bounding_box()
    assert box
    offsets = page.evaluate("({x:screenX+(outerWidth-innerWidth)/2,y:screenY+(outerHeight-innerHeight)})")
    x = int(box["x"] + box["width"] / 2 + offsets["x"])
    y = int(box["y"] + box["height"] / 2 + offsets["y"])
    for step in range(1, 26):
        subprocess.run(["xdotool", "mousemove", str(20 + (x-20)*step//25), str(20 + (y-20)*step//25)], check=True)
        time.sleep(0.018)


server = None
recorder = None
manifest = {
    "source_commit": os.environ.get("GITHUB_SHA"),
    "run_id": os.environ.get("GITHUB_RUN_ID"),
    "started_at_epoch": time.time(),
    "capture": "FFMPEG_X11GRAB_CONTINUOUS_DISPLAY",
    "master_kind": "RAW_UNEDITED_QUALIFICATION_SEGMENT",
    "final_submission_video": False,
    "model_inference": False,
    "no_owner_credentials_present_on_display": True,
    "checks": {},
}
try:
    with tempfile.TemporaryDirectory(prefix="wexspace-display-") as directory, sync_playwright() as playwright:
        server, port = start_server(Path(directory))
        manifest["process_a"] = server.pid
        browser = playwright.chromium.launch(headless=False, args=[
            "--kiosk", "--window-position=0,0", "--window-size=1280,720"])
        page = browser.new_page(no_viewport=True)
        page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
        with (OUT / "capture.log").open("w") as log:
            recorder = subprocess.Popen([
                "ffmpeg", "-y", "-f", "x11grab", "-framerate", "25",
                "-video_size", "1280x720", "-draw_mouse", "1", "-i", os.environ["DISPLAY"],
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / "segment.mp4"),
            ], stdin=subprocess.PIPE, stdout=log, stderr=log)
            time.sleep(1.5)
            move_native_mouse(page, "#label")
            page.locator("#label").click()
            page.locator("#label").fill("")
            page.locator("#label").press_sequentially("Synthetic receiving review", delay=65)
            move_native_mouse(page, "#start")
            page.locator("#start").click()
            expect(page.locator("#cursor")).to_have_text("Durable cursor: 1 / 3")
            work_id = page.locator("#work").inner_text()
            manifest["work_id"] = work_id
            manifest["checks"]["browser_create_and_read"] = "PASS"
            time.sleep(2)

            server.kill()
            server.wait(timeout=5)
            manifest["termination"] = {"signal": "SIGKILL", "return_code": server.returncode}
            assert server.returncode == -signal.SIGKILL
            move_native_mouse(page, "#refresh")
            page.locator("#refresh").click()
            expect(page.locator("#status")).to_contain_text("Service unavailable")
            time.sleep(2)

            server, restarted_port = start_server(Path(directory), port)
            assert restarted_port == port and server.pid != manifest["process_a"]
            manifest["process_b"] = server.pid
            move_native_mouse(page, "#refresh")
            page.locator("#refresh").click()
            expect(page.locator("#cursor")).to_have_text("Durable cursor: 1 / 3")
            expect(page.locator("#resume")).to_be_enabled()
            assert page.locator("#work").inner_text() == work_id
            manifest["checks"]["fresh_server_state_readback"] = "PASS"
            time.sleep(1.5)
            move_native_mouse(page, "#resume")
            page.locator("#resume").click()
            expect(page.locator("#status")).to_contain_text("HUMAN_REVIEW")
            move_native_mouse(page, "#receipt")
            page.locator("#receipt").click()
            expect(page.locator("#evidence")).to_contain_text("decision_sha256")
            receipt = json.loads(page.locator("#evidence").inner_text())
            assert receipt["work_id"] == work_id
            assert receipt["effect_counts"] == {"inspect_request": 1, "reconcile_evidence": 1, "prepare_review_package": 1}
            assert receipt["decision"]["agent_may_auto_approve"] is False
            assert receipt["decision"]["reconciliation"]["delta"] == -2
            assert receipt["evidence_chain_valid"]
            manifest["checks"].update({"exact_resume": "PASS", "no_duplicate_effect": "PASS", "human_gate": "PASS"})
            (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            page.mouse.wheel(0, 470)
            time.sleep(2)
            page.mouse.wheel(0, -470)
            time.sleep(2)
            page.screenshot(path=str(OUT / "preview.png"))
            manifest["browser_version"] = browser.version
            manifest["playwright_version"] = version("playwright")
            manifest["state"] = "QUALIFIED"
            recorder.communicate(b"q\n", timeout=20)
            recorder = None
            browser.close()
            pdf_browser = playwright.chromium.launch(headless=True)
            architecture_page = pdf_browser.new_page()
            architecture_html = Path("qualification/architecture.html").read_text()
            architecture_html = architecture_html.replace("{{SOURCE_COMMIT}}", os.environ.get("GITHUB_SHA", "local"))
            architecture_html = architecture_html.replace("{{RUN_ID}}", os.environ.get("GITHUB_RUN_ID", "local"))
            architecture_page.set_content(architecture_html)
            architecture_page.pdf(path=str(OUT / "architecture.pdf"), format="A4", print_background=True)
            pdf_browser.close()
finally:
    if recorder is not None:
        recorder.communicate(b"q\n", timeout=20)
    if server is not None and server.poll() is None:
        server.terminate()
        server.wait(timeout=10)
    manifest["ended_at_epoch"] = time.time()
    manifest.setdefault("state", "INCOMPLETE")
    movie = OUT / "segment.mp4"
    if movie.exists():
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_name,width,height,r_frame_rate,nb_frames",
            "-of", "json", str(movie)], text=True))
        manifest["media"] = probe
    manifest["sha256"] = {
        name: digest(OUT / name) for name in ["segment.mp4", "preview.png", "receipt.json", "architecture.pdf"]
        if (OUT / name).exists()
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))
