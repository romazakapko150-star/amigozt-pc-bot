"""One picture for a whole list, so prices arrive next to the product.

Telegram cannot put an image beside each line of a text message, and an
album (media group) carries no inline keyboard - which the numbered picker
depends on. So a list page is composed into a single contact sheet: each
tile shows the product's stored photo, its number, its name and its price,
and the existing keyboard stays attached to that one message.

Nothing here generates anything: it only arranges photos the Visual
Library already paid for. A product without a photo still gets a tile, with
a neutral placeholder, so numbering never shifts.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from PIL import Image, ImageDraw
from PIL.Image import Resampling

from app.services.media.build_image import (
    ACCENT,
    BACKGROUND,
    MUTED,
    PANEL,
    PRICE_GREEN,
    TEXT,
    AnyFont,
    fit_text,
    load_font,
)

logger = logging.getLogger(__name__)

#: Tile grid. Three columns read well on a phone at 1080 px wide; more than
#: nine tiles per page would make each one too small to recognise.
COLUMNS = 3
MAX_TILES = 12
WIDTH = 1080
PADDING = 24
GAP = 18
HEADER_HEIGHT = 96
TILE_TEXT_HEIGHT = 116
RADIUS = 14

#: Telegram markup that must not be drawn into the picture.
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class GridEntry:
    """One numbered product on a list page."""

    index: int
    name: str
    price_text: str
    image_path: Path | None = None


def cache_key(title: str, entries: list[GridEntry]) -> str:
    payload = "|".join(
        [
            title,
            *(
                f"{e.index}:{e.name}:{e.price_text}:{e.image_path.name if e.image_path else '-'}"
                for e in entries
            ),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _tile_image(path: Path | None, size: int) -> Image.Image:
    """The product photo, letterboxed into a square tile."""
    canvas = Image.new("RGB", (size, size), PANEL)
    if path is None or not path.is_file():
        return canvas
    try:
        with Image.open(path) as source:
            photo = source.convert("RGB")
            photo.thumbnail((size, size), Resampling.LANCZOS)
            canvas.paste(photo, ((size - photo.width) // 2, (size - photo.height) // 2))
    except (OSError, ValueError):
        logger.debug("Unreadable product image %s, using a blank tile", path)
    return canvas


def _plain(text: str) -> str:
    """Turn a Telegram label into something a drawing font can render.

    UI strings are written for Telegram: they carry HTML tags and emoji,
    neither of which belongs in a picture - the tags would be printed
    literally and the bundled system font draws emoji as tofu boxes.
    """
    without_tags = unescape(_TAG.sub("", text))
    return "".join(ch for ch in without_tags if ord(ch) < 0x2190).strip()


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: AnyFont, width: int, max_lines: int = 2
) -> list[str]:
    """Break a product name over up to ``max_lines``, eliding only at the end.

    Product names carry the numbers a customer compares on ("27\" 1440p 170Hz"),
    so cutting them off after the brand would defeat the point of the tile.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        return [fit_text(draw, text, font, width)]
    # Anything that did not fit is elided on the last line.
    consumed = len(" ".join(lines).split())
    if consumed < len(words):
        lines[-1] = fit_text(draw, lines[-1] + " " + " ".join(words[consumed:]), font, width)
    return lines


def _draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, number: str, font: AnyFont) -> None:
    """The number the customer presses, over the top-left of the photo."""
    width = max(30, int(draw.textlength(number, font=font)) + 20)
    draw.rounded_rectangle([x, y, x + width, y + 32], radius=10, fill=BACKGROUND)
    draw.text((x + 10, y + 5), number, font=font, fill=ACCENT)


def render_catalog_grid(
    title: str,
    entries: list[GridEntry],
    *,
    output_dir: Path,
    footer: str | None = None,
) -> Path | None:
    """Compose the page into one image; ``None`` when there is nothing to show.

    The result is cached by content, so paging back and forth costs nothing.
    """
    shown = entries[:MAX_TILES]
    if not shown:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"grid-{cache_key(title, shown)}.png"
    if path.exists():
        return path

    columns = min(COLUMNS, len(shown))
    rows = (len(shown) + columns - 1) // columns
    tile_size = (WIDTH - 2 * PADDING - (columns - 1) * GAP) // columns
    tile_height = tile_size + TILE_TEXT_HEIGHT
    footer_height = 44 if footer else 0
    height = HEADER_HEIGHT + rows * tile_height + (rows - 1) * GAP + PADDING + footer_height

    image = Image.new("RGB", (WIDTH, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    title_font = load_font(38, bold=True)
    badge_font = load_font(20, bold=True)
    name_font = load_font(23)
    price_font = load_font(26, bold=True)
    footer_font = load_font(19)

    draw.text(
        (PADDING, PADDING),
        fit_text(draw, _plain(title), title_font, WIDTH - 2 * PADDING),
        font=title_font,
        fill=TEXT,
    )

    for position, entry in enumerate(shown):
        column = position % columns
        row = position // columns
        x = PADDING + column * (tile_size + GAP)
        y = HEADER_HEIGHT + row * (tile_height + GAP)

        draw.rounded_rectangle([x, y, x + tile_size, y + tile_height], radius=RADIUS, fill=PANEL)
        image.paste(_tile_image(entry.image_path, tile_size), (x, y))
        # Re-round the photo's corners against the panel behind it.
        draw.rounded_rectangle(
            [x, y, x + tile_size, y + tile_height], radius=RADIUS, outline=BACKGROUND, width=3
        )
        _draw_badge(draw, x + 10, y + 10, str(entry.index), badge_font)

        text_x = x + 12
        text_width = tile_size - 24
        line_y = y + tile_size + 8
        for line in _wrap(draw, _plain(entry.name), name_font, text_width):
            draw.text((text_x, line_y), line, font=name_font, fill=TEXT)
            line_y += 28
        draw.text(
            (text_x, y + tile_size + 74),
            fit_text(draw, entry.price_text, price_font, text_width),
            font=price_font,
            fill=PRICE_GREEN,
        )

    if footer:
        draw.text(
            (PADDING, height - PADDING - 6),
            fit_text(draw, _plain(footer), footer_font, WIDTH - 2 * PADDING),
            font=footer_font,
            fill=MUTED,
        )

    image.save(path, format="PNG", optimize=True)
    logger.debug("Rendered catalogue grid %s (%s tiles)", path.name, len(shown))
    return path
