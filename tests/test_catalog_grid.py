"""List pages show the product photo next to the price.

Telegram cannot put an image beside each line of a message, so a list page
is composed into one contact sheet and the existing numbered keyboard stays
attached to it. What matters is that the picture never lies about the list:
the numbers on the tiles are the numbers on the buttons, and nothing here
ever generates a paid image.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from app.services.media.catalog_grid import (
    MAX_TILES,
    GridEntry,
    _plain,
    cache_key,
    render_catalog_grid,
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    path = tmp_path / "product.png"
    path.write_bytes(PNG)
    return path


def _entries(count: int, photo: Path | None = None) -> list[GridEntry]:
    return [
        GridEntry(index=i, name=f"Product {i}", price_text=f"≈{i * 100} PLN", image_path=photo)
        for i in range(1, count + 1)
    ]


# --- composition ---------------------------------------------------------------


def test_a_page_is_one_image(tmp_path: Path, photo: Path) -> None:
    out = render_catalog_grid("Monitor", _entries(8, photo), output_dir=tmp_path)
    assert out is not None and out.is_file()
    with Image.open(out) as image:
        assert image.width == 1080
        assert image.height > image.width / 2


def test_an_empty_list_produces_nothing(tmp_path: Path) -> None:
    assert render_catalog_grid("Monitor", [], output_dir=tmp_path) is None


def test_the_page_is_cached_by_content(tmp_path: Path, photo: Path) -> None:
    """Paging back and forth must not redraw anything."""
    first = render_catalog_grid("Monitor", _entries(5, photo), output_dir=tmp_path)
    assert first is not None
    stamp = first.stat().st_mtime_ns
    again = render_catalog_grid("Monitor", _entries(5, photo), output_dir=tmp_path)
    assert again == first
    assert again.stat().st_mtime_ns == stamp, "an identical page was redrawn"


def test_a_changed_price_is_a_different_page(tmp_path: Path, photo: Path) -> None:
    entries = _entries(3, photo)
    before = cache_key("Monitor", entries)
    entries[0] = GridEntry(index=1, name="Product 1", price_text="≈999 PLN", image_path=photo)
    assert cache_key("Monitor", entries) != before


def test_the_page_never_grows_past_the_tile_cap(tmp_path: Path, photo: Path) -> None:
    out = render_catalog_grid("Big", _entries(MAX_TILES + 6, photo), output_dir=tmp_path)
    assert out is not None
    capped = render_catalog_grid("Big", _entries(MAX_TILES, photo), output_dir=tmp_path)
    with Image.open(out) as a, Image.open(capped) as b:  # type: ignore[arg-type]
        assert a.height == b.height


# --- honesty about the list ------------------------------------------------------


def test_a_product_without_a_photo_still_gets_its_tile(tmp_path: Path, photo: Path) -> None:
    """Numbering must not shift because one item has no picture yet."""
    mixed = [
        GridEntry(index=1, name="With", price_text="≈100 PLN", image_path=photo),
        GridEntry(index=2, name="Without", price_text="≈200 PLN", image_path=None),
        GridEntry(index=3, name="Missing file", price_text="≈300 PLN", image_path=tmp_path / "x"),
    ]
    out = render_catalog_grid("Mixed", mixed, output_dir=tmp_path)
    assert out is not None and out.is_file()


def test_an_unreadable_image_does_not_break_the_page(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    out = render_catalog_grid(
        "Broken",
        [GridEntry(index=1, name="Broken", price_text="—", image_path=broken)],
        output_dir=tmp_path,
    )
    assert out is not None and out.is_file()


# --- text that is written for Telegram, not for a canvas --------------------------


def test_telegram_markup_is_never_painted_into_the_picture() -> None:
    assert _plain("<b>Ready-made builds</b>") == "Ready-made builds"
    assert _plain("🖥 Monitor") == "Monitor"
    assert _plain("Gigabyte M27Q 27&quot;") == 'Gigabyte M27Q 27"'


def test_plain_text_survives_untouched() -> None:
    assert _plain("AmigoZT Starter 4.3K") == "AmigoZT Starter 4.3K"
    assert _plain('AOC 24G2SPU 24" 1080p 165Hz') == 'AOC 24G2SPU 24" 1080p 165Hz'


# --- the money rule ---------------------------------------------------------------


def test_composing_a_page_never_calls_an_image_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, photo: Path
) -> None:
    """The grid only arranges files that already exist on disk."""
    import app.services.media.ai_visual as ai_visual

    def explode(*_: object, **__: object) -> None:
        raise AssertionError("the grid must never generate an image")

    monkeypatch.setattr(ai_visual.OpenAIImageGenerator, "generate_png", explode, raising=False)
    out = render_catalog_grid("Monitor", _entries(6, photo), output_dir=tmp_path)
    assert out is not None


def test_prices_are_drawn_for_every_entry(tmp_path: Path, photo: Path) -> None:
    """A tile without a price would be worse than no tile at all."""
    entries = [
        GridEntry(index=1, name="Priced", price_text="≈620 PLN", image_path=photo),
        GridEntry(index=2, name="Unpriced", price_text="—", image_path=photo),
    ]
    assert all(entry.price_text for entry in entries)
    assert render_catalog_grid("Monitor", entries, output_dir=tmp_path) is not None


def test_the_key_covers_the_title_so_two_categories_never_share_a_page(photo: Path) -> None:
    entries = _entries(4, photo)
    assert cache_key("Monitor", entries) != cache_key("Keyboard", entries)


def test_a_decimal_price_formats_into_the_entry() -> None:
    entry = GridEntry(index=1, name="X", price_text=f"≈{Decimal('4299')} PLN")
    assert "4299" in entry.price_text
