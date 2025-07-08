# test_cdp.py  –  minimal example that produces a non-empty .webm
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

VIDEO_DIR = Path(__file__).parent / "videos"
VIDEO_DIR.mkdir(exist_ok=True)

payload = {"record": True}
resp = requests.post("http://localhost:8000/sessions", json=payload)
resp.raise_for_status()
cdp_url = resp.json()["connectUrl"]

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp(cdp_url)

    context = browser.new_context(
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1280, "height": 720},
    )

    page = context.new_page()
    page.goto("https://example.org")
    page.screenshot(path="example.png")

    # Sleep to simulate some activity
    page.wait_for_timeout(2000)  # wait 2 seconds

    # 1️⃣ Close the page *first* (optional but tidy)
    page.close()

    # 2️⃣ Close the context – this flushes and finalises the .webm
    context.close()

    # 3️⃣ NOW the video file is complete
    video_path = page.video.path()
    print("✅ Video saved to:", video_path)
    assert Path(video_path).stat().st_size > 0, "Video is still empty!"

    browser.close()
