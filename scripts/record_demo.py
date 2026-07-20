#!/usr/bin/env python3
"""Record a demo GIF of the human-in-the-loop agent flow.

Drives the running app with Playwright, screenshots the key moments (ask →
generative approval card → per-field edit → approve → streamed answer), and
stitches them into ``docs/demo.gif`` with Pillow.

Prereqs (both servers running):
    cd backend  && USE_MOCK_LLM=true python main.py     # http://localhost:8000
    cd frontend && npm run build && npm run start        # http://localhost:3000

Then, from the repo root:
    pip install playwright pillow
    python scripts/record_demo.py

Tip: for nicer content, run the backend with a real model
(``LLM_MODEL`` + a provider key) so the answer streams real text.
"""

from __future__ import annotations

import os

from PIL import Image
from playwright.sync_api import sync_playwright

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")

URL = os.environ.get("DEMO_URL", "http://127.0.0.1:3000")
CHROME = os.environ.get("DEMO_CHROME", "/opt/pw-browsers/chromium")
FRAME_DIR = os.environ.get("DEMO_FRAME_DIR", "/tmp/demo-frames")
OUT = os.environ.get("DEMO_OUT", "docs/demo.gif")
QUERY = "What are the latest advances in solid-state batteries?"
GIF_WIDTH = 900

os.makedirs(FRAME_DIR, exist_ok=True)
frames: list[tuple[str, int]] = []  # (png path, duration ms)


def shot(page, name: str, duration_ms: int) -> None:
    path = os.path.join(FRAME_DIR, f"{name}.png")
    page.screenshot(path=path)
    frames.append((path, duration_ms))


def record() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--force-color-profile=srgb"],
        )
        ctx = browser.new_context(
            viewport={"width": 1120, "height": 760}, device_scale_factor=2
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1300)  # let the /capabilities status strip load

        # Switch to the Agent engine (model-driven loop with tool approval).
        page.get_by_role("button", name="Agent", exact=True).click()
        page.wait_for_timeout(800)
        shot(page, "01-welcome", 1500)

        # Ask a research question.
        box = page.get_by_role("textbox").first
        box.click()
        box.press_sequentially(QUERY, delay=32)
        page.wait_for_timeout(300)
        shot(page, "02-typed", 1100)

        # Submit → the agent pauses for approval on web_search.
        box.press("Enter")
        page.get_by_text("Human approval required").wait_for(timeout=20000)
        page.wait_for_timeout(600)
        shot(page, "03-approval", 2300)

        # Show the per-field (generative) editor, then cancel.
        try:
            page.locator("button", has_text="Edit").first.click()
            page.wait_for_timeout(700)
            shot(page, "04-edit", 1900)
            page.locator("button", has_text="Cancel").first.click()
            page.wait_for_timeout(400)
        except Exception as exc:  # pragma: no cover
            print("edit step skipped:", exc)

        # Approve → the answer streams in.
        page.locator("button", has_text="Approve").first.click()
        page.wait_for_timeout(800)
        shot(page, "05-approved", 900)
        page.wait_for_timeout(1000)
        shot(page, "06-stream", 900)
        page.wait_for_timeout(1600)
        shot(page, "07-answer", 2800)

        browser.close()


def build_gif() -> None:
    imgs, durations = [], []
    for path, dur in frames:
        im = Image.open(path).convert("RGB")
        if im.width > GIF_WIDTH:
            h = round(im.height * GIF_WIDTH / im.width)
            im = im.resize((GIF_WIDTH, h), Image.LANCZOS)
        imgs.append(im.quantize(colors=200, method=Image.MEDIANCUT))
        durations.append(dur)

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    imgs[0].save(
        OUT,
        save_all=True,
        append_images=imgs[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    size_kb = os.path.getsize(OUT) // 1024
    print(f"wrote {OUT} ({len(imgs)} frames, {size_kb} KB)")


if __name__ == "__main__":
    record()
    build_gif()
