"""Where generated media lives."""

from __future__ import annotations

from pathlib import Path

#: Rendered build cards. Regenerable, so it is git-ignored and safe to wipe.
MEDIA_ROOT = Path(__file__).resolve().parents[3] / "media"
BUILD_IMAGE_DIR = MEDIA_ROOT / "builds"
#: Photorealistic renders from the image API. Paid per render, so cached.
AI_IMAGE_DIR = MEDIA_ROOT / "ai"
