# screencast_test.py
"""
Streams a Chromium screencast over CDP, saves frames as JPEGs,
then stitches them into session.mp4 with ffmpeg.
"""
import base64, subprocess, pathlib
from playwright.sync_api import sync_playwright
import requests

ROOT      = pathlib.Path(__file__).parent
FRAME_DIR = ROOT / "frames"
VIDEO_DIR = ROOT / "videos"
FRAME_DIR.mkdir(exist_ok=True, parents=True)
VIDEO_DIR.mkdir(exist_ok=True, parents=True)

# ----- spin up your remote browser -------------------------------------------------
resp = requests.post(
    "http://localhost:8000/sessions",
    json={"client_id": "pytest", "record": True}
)
resp.raise_for_status()
cdp_url = resp.json()["connectUrl"]

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp(cdp_url)
    ctx      = browser.new_context()
    page     = ctx.new_page()

    # ----- start the screencast -----------------------------------------------------
    cdp = ctx.new_cdp_session(page)
    cdp.send("Page.startScreencast", {
        "format": "jpeg",          # jpeg | png
        "quality": 85,             # 0-100, jpeg only
        "maxWidth": 1280,
        "maxHeight": 720,
        "everyNthFrame": 1         # take every frame
    })

    frame_no = 0
    def on_frame(ev):
        global frame_no 
        frame_no += 1
        jpeg_bytes = base64.b64decode(ev["data"])
        (FRAME_DIR / f"{frame_no:06d}.jpg").write_bytes(jpeg_bytes)

        # ACK is mandatory or Chrome pauses the stream:
        cdp.send("Page.screencastFrameAck", { "sessionId": ev["sessionId"] })

    cdp.on("Page.screencastFrame", on_frame)

    # ----- do something visible -----------------------------------------------------
    page.goto("https://example.org")
    page.wait_for_timeout(3000)

    # ----- stop the screencast and clean up -----------------------------------------
    cdp.send("Page.stopScreencast")
    ctx.close()
    browser.close()

# ----- convert the JPEG sequence to an MP4 -----------------------------------------
mp4_path = VIDEO_DIR / "session.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-framerate", "30",
    "-pattern_type", "glob",
    "-i", str(FRAME_DIR / "*.jpg"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    str(mp4_path)
], check=True)

print("🎞  Screencast ready →", mp4_path)
