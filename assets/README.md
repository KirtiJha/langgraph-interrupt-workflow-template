# Assets

Drop demo media for the README here.

## Add a demo GIF (recommended)

1. **Run the app** (zero config — no API keys needed):
   ```bash
   # terminal 1
   cd backend && python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt && cp .env.example .env && python main.py
   # terminal 2
   cd frontend && npm install && npm run dev
   ```
   Open http://localhost:3000.

2. **Record a ~10–20s clip** that shows the workflow pausing at an interrupt and
   resuming after you pick an option. Good recorders:
   - **macOS:** [Kap](https://getkap.co/) (exports GIF directly), or QuickTime → convert.
   - **Windows:** [ScreenToGif](https://www.screentogif.com/).
   - **Linux:** [Peek](https://github.com/phw/peek).
   - **Cross-platform:** [LICEcap](https://www.cockos.com/licecap/).

3. **Optimize** it (GitHub renders inline up to ~10 MB; smaller is better):
   ```bash
   # using gifsicle
   gifsicle -O3 --lossy=80 --colors 128 raw.gif -o demo.gif
   ```
   Or upload to https://ezgif.com/optimize. Aim for ≤ ~1200px wide and a few MB.

4. **Save it as** `assets/demo.gif` and, in the root `README.md`, uncomment:
   ```markdown
   ![LangGraph interrupt workflow demo](assets/demo.gif)
   ```
   (and remove the "coming soon" placeholder line).

## Prefer a static screenshot?

Save a PNG as `assets/demo.png` and reference it the same way. Screenshots load
faster but a GIF showing the interrupt → resume flow is far more compelling for
this template.

## Tip: host large media outside git

For clips over ~10 MB, drag the file into a GitHub issue/PR comment or release —
GitHub returns a `user-images.githubusercontent.com` URL you can embed in the
README without bloating the repo.
