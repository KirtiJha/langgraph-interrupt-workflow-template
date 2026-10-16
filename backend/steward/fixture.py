"""A sample repository for the zero-config demo, CI and the offline pilot.

``acme/pixelforge`` is a small image-processing CLI with the backlog every
maintainer recognises: bugs with and without a reproduction, a duplicate, a
question answerable from the docs, feature requests, stale threads, a stale
PR, a first-time contributor's PR, and a release that's overdue.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SAMPLE_REPO_NAME = "acme/pixelforge"


def _ago(days: int, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


README = """# pixelforge

Fast, scriptable image processing from the command line.

```bash
pip install pixelforge
pixelforge resize photo.jpg --width 800
pixelforge convert *.png --to webp --quality 80
pixelforge batch ./photos --pipeline pipeline.yaml
```

## Features
- Resize, crop, rotate, convert (jpg, png, webp, avif, heic via `pixelforge[heic]`)
- Batch pipelines in YAML with parallel workers (`--workers N`, default = CPU count)
- Metadata: `pixelforge meta photo.jpg` prints EXIF; `--strip` removes it

## Memory
Large batches stream files one at a time. Set `PIXELFORGE_MAX_PIXELS` to raise the
decompression-bomb limit (default 89,478,485 pixels, the same as Pillow).

## Contributing
See CONTRIBUTING.md. Bug reports need a minimal reproduction and `pixelforge --version`.
We label issues `needs-repro`, `bug`, `enhancement`, `question`, `good first issue`.
"""

LABELS = [
    {"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
    {"name": "enhancement", "color": "a2eeef", "description": "New feature or request"},
    {"name": "question", "color": "d876e3", "description": "Further information is requested"},
    {"name": "needs-repro", "color": "fbca04", "description": "Needs a minimal reproduction"},
    {"name": "duplicate", "color": "cfd3d7", "description": "This issue or pull request already exists"},
    {"name": "good first issue", "color": "7057ff", "description": "Good for newcomers"},
    {"name": "stale", "color": "ededed", "description": "No activity for a long time"},
    {"name": "docs", "color": "0075ca", "description": "Documentation"},
    {"name": "help wanted", "color": "008672", "description": "Extra attention is needed"},
]

ISSUES = [
    {"number": 101, "title": "resize crashes with 'image file is truncated' on some JPEGs", "author": "mira-k",
     "author_association": "NONE", "labels": [], "created_at": _ago(1), "updated_at": _ago(1), "comments": 0,
     "body": "Running `pixelforge resize IMG_4471.jpg --width 800` fails with:\n\n```\nOSError: image file is truncated (12 bytes not processed)\n```\n\npixelforge 2.3.1, Python 3.12, macOS 14. The file opens fine in Preview. Attached: IMG_4471.jpg (2.1 MB).",
     "thread": []},
    {"number": 102, "title": "It doesn't work", "author": "newbie42", "author_association": "NONE", "labels": [],
     "created_at": _ago(2), "updated_at": _ago(2), "comments": 0,
     "body": "I installed it and it doesn't work. Please fix.", "thread": []},
    {"number": 103, "title": "How do I keep EXIF data when converting to webp?", "author": "photofan",
     "author_association": "NONE", "labels": [], "created_at": _ago(3), "updated_at": _ago(3), "comments": 0,
     "body": "Converting with `pixelforge convert a.jpg --to webp` drops the EXIF. Is there an option to keep it? Couldn't find it in the README.",
     "thread": []},
    {"number": 104, "title": "Feature: --dry-run for batch pipelines", "author": "ops-sam", "author_association": "NONE",
     "labels": [], "created_at": _ago(4), "updated_at": _ago(4), "comments": 1,
     "body": "It would be great to see what a pipeline *would* do before running it on 40k files. Something like `pixelforge batch ./photos --pipeline p.yaml --dry-run`.",
     "thread": [{"author": "dev-lee", "body": "+1, we'd use this.", "created_at": _ago(3)}]},
    {"number": 105, "title": "Truncated JPEG error when resizing", "author": "jdoe", "author_association": "NONE",
     "labels": [], "created_at": _ago(5), "updated_at": _ago(5), "comments": 0,
     "body": "Same as the title — `OSError: image file is truncated` when resizing a photo from my phone. Version 2.3.1.",
     "thread": []},
    {"number": 106, "title": "Batch with --workers 16 uses 20 GB of RAM", "author": "bigdata-bo", "author_association": "NONE",
     "labels": ["bug"], "created_at": _ago(9), "updated_at": _ago(2), "comments": 4,
     "body": "Running `pixelforge batch ./scans --pipeline ocr-prep.yaml --workers 16` on 1,200 TIFFs climbs to 20 GB RSS and gets OOM-killed. Each TIFF is ~60 MB. Expected: memory bounded by workers × one image.\n\npixelforge 2.3.1, Linux, Python 3.11.",
     "thread": [{"author": "maintainer-ana", "body": "Thanks — can you share one of the TIFFs or its dimensions?", "created_at": _ago(8)},
                {"author": "bigdata-bo", "body": "12,000 × 9,000 px, 16-bit grayscale.", "created_at": _ago(7)},
                {"author": "maintainer-ana", "body": "That's 108 MP each; 16 workers × decoded buffer ≈ 20 GB. We should cap decoded pixels per worker.", "created_at": _ago(6)},
                {"author": "dev-lee", "body": "I can take this if nobody else is on it.", "created_at": _ago(2)}]},
    {"number": 107, "title": "Support AVIF output", "author": "web-perf", "author_association": "NONE", "labels": ["enhancement"],
     "created_at": _ago(100), "updated_at": _ago(70), "comments": 2,
     "body": "AVIF is now widely supported in browsers. Could `convert --to avif` be added?",
     "thread": [{"author": "maintainer-ana", "body": "Yes — this landed in 2.3.0 via pillow-avif. Closing when docs are updated.", "created_at": _ago(72)},
                {"author": "web-perf", "body": "Great, thanks!", "created_at": _ago(70)}]},
    {"number": 108, "title": "Typo in README: 'decompresion'", "author": "spellcheck-sue", "author_association": "NONE",
     "labels": [], "created_at": _ago(6), "updated_at": _ago(6), "comments": 0,
     "body": "README says 'decompresion-bomb limit'. Should be 'decompression'. Happy to send a PR.", "thread": []},
    {"number": 109, "title": "Windows: pipeline.yaml paths with backslashes are not found", "author": "win-wendy",
     "author_association": "NONE", "labels": [], "created_at": _ago(12), "updated_at": _ago(12), "comments": 0,
     "body": "On Windows 11 a pipeline with `input: photos\\raw` fails with FileNotFoundError, while `photos/raw` works. pixelforge 2.3.1, Python 3.12.\n\nRepro:\n```yaml\ninput: photos\\raw\nsteps: [{resize: {width: 800}}]\n```",
     "thread": []},
    {"number": 110, "title": "Add --quality to resize", "author": "old-timer", "author_association": "NONE", "labels": ["enhancement"],
     "created_at": _ago(200), "updated_at": _ago(140), "comments": 1,
     "body": "resize always re-encodes at default quality; please add --quality like convert has.",
     "thread": [{"author": "maintainer-ana", "body": "Reasonable. PRs welcome.", "created_at": _ago(140)}]},
    {"number": 111, "title": "Crash on HEIC from iPhone 15", "author": "iphone-ira", "author_association": "NONE", "labels": [],
     "created_at": _ago(95), "updated_at": _ago(95), "comments": 0,
     "body": "Crashes on HEIC files. Stack trace attached.", "thread": []},
    {"number": 112, "title": "Question: can pipelines call custom Python functions?", "author": "scripter-sal",
     "author_association": "NONE", "labels": [], "created_at": _ago(7), "updated_at": _ago(7), "comments": 0,
     "body": "I'd like a step that calls my own function (watermarking). Is there a plugin mechanism?", "thread": []},
    # Pull requests
    {"number": 113, "title": "Fix README typo (decompression)", "author": "spellcheck-sue", "author_association": "FIRST_TIME_CONTRIBUTOR",
     "labels": [], "created_at": _ago(5), "updated_at": _ago(5), "comments": 0, "is_pr": True,
     "body": "Fixes #108.",
     "pull": {"number": 113, "title": "Fix README typo (decompression)", "author": "spellcheck-sue", "draft": False, "mergeable": True,
              "additions": 1, "deletions": 1, "changed_files": 1, "base": "main", "head": "fix-typo",
              "files": [{"path": "README.md", "status": "modified", "additions": 1, "deletions": 1,
                         "patch": "-Set `PIXELFORGE_MAX_PIXELS` to raise the decompresion-bomb limit\n+Set `PIXELFORGE_MAX_PIXELS` to raise the decompression-bomb limit"}]},
     "thread": []},
    {"number": 114, "title": "Cap decoded pixels per worker (fixes #106)", "author": "dev-lee", "author_association": "CONTRIBUTOR",
     "labels": [], "created_at": _ago(1), "updated_at": _ago(1), "comments": 0, "is_pr": True,
     "body": "Adds `--max-worker-pixels` (default 50 MP). Images above the cap are decoded with `draft()` downscaling first. Fixes #106.",
     "pull": {"number": 114, "title": "Cap decoded pixels per worker (fixes #106)", "author": "dev-lee", "draft": False, "mergeable": True,
              "additions": 84, "deletions": 6, "changed_files": 3, "base": "main", "head": "cap-worker-pixels",
              "files": [{"path": "pixelforge/batch.py", "status": "modified", "additions": 61, "deletions": 5, "patch": "+    max_pixels = args.max_worker_pixels or DEFAULT_MAX_WORKER_PIXELS\n+    if w * h > max_pixels:\n+        img.draft(img.mode, (w // 2, h // 2))"},
                        {"path": "tests/test_batch.py", "status": "modified", "additions": 20, "deletions": 0, "patch": "+def test_large_image_is_downscaled_before_decode(): ..."},
                        {"path": "README.md", "status": "modified", "additions": 3, "deletions": 1, "patch": "+`--max-worker-pixels` caps memory per worker."}]},
     "thread": []},
    {"number": 115, "title": "WIP: rewrite CLI with click", "author": "refactor-rex", "author_association": "NONE",
     "labels": [], "created_at": _ago(120), "updated_at": _ago(95), "comments": 2, "is_pr": True,
     "body": "Big refactor, not finished.",
     "pull": {"number": 115, "title": "WIP: rewrite CLI with click", "author": "refactor-rex", "draft": True, "mergeable": False,
              "additions": 1240, "deletions": 980, "changed_files": 22, "base": "main", "head": "click-rewrite", "files": []},
     "thread": [{"author": "maintainer-ana", "body": "This conflicts with main now — are you still working on it?", "created_at": _ago(100)},
                {"author": "refactor-rex", "body": "Will rebase soon.", "created_at": _ago(95)}]},
]

FILES = {
    "README.md": README,
    "CONTRIBUTING.md": "# Contributing\n\nOpen an issue first for anything bigger than a typo. Run `make test`. Bug reports need a minimal reproduction and the output of `pixelforge --version`.\n",
    "pixelforge/convert.py": "def convert(path, to, quality=80, keep_metadata=False):\n    \"\"\"Convert an image. keep_metadata=True copies EXIF where the target format supports it (jpg, webp, avif).\"\"\"\n    ...\n",
    "pixelforge/cli.py": "# CLI entry points\n# convert: --to --quality --keep-metadata\n# resize: --width --height\n# batch: --pipeline --workers\n",
    "pixelforge/pipeline.py": "# YAML pipelines. Steps: resize, crop, rotate, convert, strip.\n# No plugin mechanism yet — see issue #112.\n",
    "CHANGELOG.md": "# Changelog\n\n## 2.3.1 — 2026-08-02\n- Fix webp quality flag\n\n## 2.3.0 — 2026-07-10\n- AVIF output via pillow-avif\n",
}

RELEASE = {
    "last_tag": "v2.3.1",
    "commits": [
        {"sha": "a1b2c3d", "message": "Handle truncated JPEGs: load with LOAD_TRUNCATED_IMAGES and warn (#101)", "author": "maintainer-ana"},
        {"sha": "b2c3d4e", "message": "Normalise Windows path separators in pipeline inputs (#109)", "author": "maintainer-ana"},
        {"sha": "c3d4e5f", "message": "docs: document --keep-metadata for convert", "author": "maintainer-ana"},
        {"sha": "d4e5f6a", "message": "Add --dry-run to batch (#104)", "author": "ops-sam"},
        {"sha": "e5f6a7b", "message": "ci: test on Python 3.13", "author": "maintainer-ana"},
        {"sha": "f6a7b8c", "message": "Fix README typo", "author": "spellcheck-sue"},
    ],
}

SAMPLE_REPO = {
    "repo": {"full_name": SAMPLE_REPO_NAME, "description": "Fast, scriptable image processing from the command line.",
             "default_branch": "main", "stars": 1843, "open_issues": 15, "url": "https://github.com/acme/pixelforge",
             "owner": "acme", "maintainer": "maintainer-ana", "pushed_at": _ago(1), "has_issues": True},
    "labels": LABELS,
    "issues": ISSUES,
    "readme": README,
    "files": FILES,
    "release": RELEASE,
}
