#!/usr/bin/env python3
"""Record an end-to-end demo GIF of the template's main features.

Drives the running app with Playwright through a short tour and stitches the
key moments into ``docs/demo.gif`` with Pillow:

  1. Agent engine — ask → generative approval card (approve / edit / answer /
     reject) → per-field edit → approve → streamed answer with live tool progress
  2. Workflow engine — multi-step human-in-the-loop (plan → direction → format)
     with parallel `Send` research
  3. Time travel — rewind to an earlier checkpoint

Prereqs (both servers running):
    cd backend  && python main.py                        # http://localhost:8000
    cd frontend && npm run build && npm run start          # http://localhost:3000

Then, from the repo root:
    pip install playwright pillow
    python scripts/record_demo.py

Use a real model for real answers (recommended for the committed GIF):
    cd backend
    LLM_MODEL=gemini-3.5-flash LLM_PROVIDER=google_genai GOOGLE_API_KEY=... \
      RESEARCH_MAX_SUBQUERIES=2 python main.py
`RESEARCH_MAX_SUBQUERIES` keeps the parallel research within free-tier limits.
Set ``DEMO_SLOW=1`` to lengthen waits for slower models.
"""

from __future__ import annotations

import os

from PIL import Image
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")

URL = os.environ.get("DEMO_URL", "http://127.0.0.1:3000")
CHROME = os.environ.get("DEMO_CHROME", "/opt/pw-browsers/chromium")
FRAME_DIR = os.environ.get("DEMO_FRAME_DIR", "/tmp/demo-frames")
OUT = os.environ.get("DEMO_OUT", "docs/demo.gif")
GIF_WIDTH = int(os.environ.get("DEMO_WIDTH", "860"))
# Real models are slower — allow generous waits for interrupts to appear.
SETTLE = 6 if os.environ.get("DEMO_SLOW") else 3
WAIT = 90_000  # ms to wait for an interrupt / answer to appear

os.makedirs(FRAME_DIR, exist_ok=True)
frames: list[tuple[str, int]] = []


def shot(page, name: str, duration_ms: int) -> None:
    path = os.path.join(FRAME_DIR, f"{name}.png")
    page.screenshot(path=path)
    frames.append((path, duration_ms))
    print("  captured", name)


def btn(page, text: str):
    return page.locator("button", has_text=text).first


def wait_for_answer(page) -> None:
    """Wait for a streamed answer to finish (the 'Processing…' indicator clears)."""
    try:  # it may appear briefly...
        page.get_by_text("Processing your request").wait_for(timeout=8000)
    except PWTimeout:
        pass
    try:  # ...then wait for it to go away once the answer has rendered.
        page.get_by_text("Processing your request").wait_for(state="hidden", timeout=WAIT)
    except PWTimeout:
        pass
    page.wait_for_timeout(SETTLE * 300)


def record() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME, headless=True, args=["--force-color-profile=srgb"]
        )
        ctx = browser.new_context(
            viewport={"width": 1120, "height": 780}, device_scale_factor=2
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1500)  # let the /capabilities status strip load

        # ── Scene 1: Agent engine — generative approval card ─────────────────
        try:
            page.get_by_role("button", name="Agent", exact=True).click()
            page.wait_for_timeout(700)
            shot(page, "01-welcome", 1600)

            box = page.get_by_role("textbox").first
            box.click()
            box.press_sequentially(
                "Use web_search to find and summarize recent solid-state battery advances.",
                delay=22,
            )
            page.wait_for_timeout(300)
            shot(page, "02-typed", 1100)

            box.press("Enter")
            page.get_by_text("Human approval required").wait_for(timeout=WAIT)
            page.wait_for_timeout(SETTLE * 100)
            shot(page, "03-approval-card", 2400)

            btn(page, "Edit").click()
            page.wait_for_timeout(700)
            shot(page, "04-edit-args", 2000)
            btn(page, "Cancel").click()
            page.wait_for_timeout(400)

            btn(page, "Approve").click()
            wait_for_answer(page)
            shot(page, "05-agent-answer", 2800)
        except Exception as exc:  # pragma: no cover
            print("scene 1 (agent) partial:", exc)

        # ── Scene 2: Workflow engine — multi-step HITL + parallel research ───
        try:
            page.get_by_role("button", name="Workflow", exact=True).click()
            page.wait_for_timeout(700)
            box = page.get_by_role("textbox").first
            box.click()
            box.press_sequentially(
                "Compare solid-state and lithium-ion batteries.", delay=22
            )
            box.press("Enter")
            btn(page, "Proceed").wait_for(timeout=WAIT)
            page.wait_for_timeout(SETTLE * 100)
            shot(page, "06-workflow-plan", 2400)

            btn(page, "Proceed").click()
            # Parallel research runs, then the direction interrupt appears.
            btn(page, "Technical").wait_for(timeout=WAIT)
            page.wait_for_timeout(SETTLE * 100)
            shot(page, "07-parallel-research", 2400)

            btn(page, "Technical").click()
            btn(page, "Executive").wait_for(timeout=WAIT)
            page.wait_for_timeout(SETTLE * 100)
            shot(page, "08-format-choice", 2200)

            btn(page, "Executive").click()
            wait_for_answer(page)
            shot(page, "09-workflow-answer", 2800)
        except Exception as exc:  # pragma: no cover
            print("scene 2 (workflow) partial:", exc)

        # ── Scene 3: Time travel ─────────────────────────────────────────────
        try:
            page.get_by_role("button", name="History").click()
            page.get_by_text("Rewind to an earlier step").wait_for(timeout=15_000)
            page.wait_for_timeout(600)
            shot(page, "10-time-travel", 2800)
        except Exception as exc:  # pragma: no cover
            print("scene 3 (time travel) partial:", exc)

        browser.close()


def build_gif() -> None:
    if not frames:
        raise SystemExit("No frames captured — is the app running at " + URL + "?")
    imgs, durations = [], []
    for path, dur in frames:
        im = Image.open(path).convert("RGB")
        if im.width > GIF_WIDTH:
            h = round(im.height * GIF_WIDTH / im.width)
            im = im.resize((GIF_WIDTH, h), Image.LANCZOS)
        imgs.append(im.quantize(colors=180, method=Image.MEDIANCUT))
        durations.append(dur)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    imgs[0].save(
        OUT, save_all=True, append_images=imgs[1:], duration=durations,
        loop=0, optimize=True, disposal=2,
    )
    print(f"wrote {OUT} ({len(imgs)} frames, {os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    record()
    build_gif()
