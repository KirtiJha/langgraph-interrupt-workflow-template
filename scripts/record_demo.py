#!/usr/bin/env python3
"""Record the Mission Control demo GIF (``docs/demo.gif``).

Drives the running app with Playwright through one mission and stitches the
key moments together with Pillow:

  1. Gallery → launch "Plan Mom's 60th birthday dinner" (balanced autonomy)
  2. The agent reads the world, compares venues, and asks which one
  3. An approval with a risk score and a wallet preview → reject with a reason
  4. The runner-up → edit the deposit → approve
  5. Invites + calendar → approve all → mission report
  6. Rewind → branch from an earlier decision

Prereqs (both servers running):
    cd backend  && python main.py                        # http://localhost:8000
    cd frontend && npm run build && npm run start          # http://localhost:3000

Then, from the repo root:
    pip install playwright pillow
    python scripts/record_demo.py
"""

from __future__ import annotations

import os
import sys
import tempfile

from PIL import Image
from playwright.sync_api import sync_playwright

URL = os.environ.get("DEMO_URL", "http://localhost:3000")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "demo.gif")
WIDTH = 1280


def wait_for_turn(page, timeout=60000):
    page.wait_for_function(
        "() => document.querySelector('[aria-label=\"Decisions\"]') || document.body.textContent.includes('Mission report')",
        timeout=timeout,
    )
    page.wait_for_timeout(700)


def main() -> None:
    frames: list[tuple[str, float]] = []  # (path, seconds)
    tmp = tempfile.mkdtemp()

    def shot(page, name, seconds=2.2):
        path = os.path.join(tmp, f"{len(frames):02d}-{name}.png")
        page.screenshot(path=path)
        frames.append((path, seconds))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH"))
        page = browser.new_context(viewport={"width": WIDTH, "height": 800}, device_scale_factor=1).new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(600)
        shot(page, "gallery", 2.5)
        page.get_by_role("radio", name="Balanced").click()
        page.wait_for_timeout(300)
        shot(page, "autonomy", 1.4)
        page.get_by_role("button", name="Plan Mom's 60th birthday dinner").click()
        page.wait_for_timeout(1500)
        shot(page, "reading", 1.6)
        wait_for_turn(page)
        shot(page, "question", 2.4)
        page.get_by_role("button", name="Olive & Fig").first.click()
        wait_for_turn(page)
        shot(page, "approval", 3.0)
        page.get_by_role("button", name="Reject").first.click()
        page.get_by_placeholder("Too expensive").fill("Too far for Grandma")
        page.wait_for_timeout(400)
        shot(page, "reject", 1.8)
        page.get_by_role("button", name="Reject", exact=True).last.click()
        wait_for_turn(page)
        shot(page, "runner-up", 2.4)
        page.get_by_role("button", name="Edit").first.click()
        page.get_by_label("amount").fill("140")
        page.wait_for_timeout(300)
        shot(page, "edit", 2.0)
        page.get_by_role("button", name="Run with these changes").click()
        wait_for_turn(page)
        shot(page, "invites", 2.6)
        page.get_by_role("button", name="Approve all").click()
        page.wait_for_function("() => document.body.textContent.includes('Mission report')", timeout=60000)
        page.wait_for_timeout(900)
        shot(page, "report", 3.2)
        page.get_by_role("button", name="Rewind").click()
        page.get_by_role("button", name="Branch from here").first.wait_for(timeout=10000)
        page.wait_for_timeout(300)
        shot(page, "history", 2.2)
        page.get_by_role("button", name="Branch from here").nth(1).click()
        wait_for_turn(page)
        shot(page, "branch", 3.0)
        browser.close()

    images = [Image.open(p).convert("P", palette=Image.ADAPTIVE, colors=128) for p, _ in frames]
    durations = [int(s * 1000) for _, s in frames]
    images[0].save(OUT, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB, {len(frames)} frames)")


if __name__ == "__main__":
    sys.exit(main())
