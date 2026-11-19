"""Build-card images.

Draws what the machine will look like: the case in its real finish, the glass
side panel, the graphics card sized to its actual length, the cooler as an air
tower or an AIO radiator, the fans that are actually in the case - lit in the
accent colour of the chosen :class:`VisualPreset` - next to the part list and
the price.

What this is not: a photograph. AmigoZT has no licensed product photography
yet, and inventing retailer image URLs would produce broken links and pass off
someone else's photo as ours. Every card says so in its footer.
"""

from __future__ import annotations

import hashlib
import logging
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.domain.components import (
    PC_CATEGORIES,
    CaseSpec,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    GpuSpec,
)
from app.domain.labels import format_price_pln
from app.services.media.presets import RGB, CaseFinish, VisualPreset, default_preset

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1080, 1080
MARGIN = 56

BACKGROUND = (13, 17, 23)
PANEL = (22, 27, 34)
ACCENT = (88, 166, 255)
TEXT = (230, 237, 243)
MUTED = (125, 133, 144)
PRICE_GREEN = (63, 185, 80)

FONT_CANDIDATES = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)
BOLD_CANDIDATES = (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)

CATEGORY_LABELS: dict[ComponentCategory, str] = {
    ComponentCategory.CPU: "CPU",
    ComponentCategory.GPU: "GPU",
    ComponentCategory.MOTHERBOARD: "MB",
    ComponentCategory.RAM: "RAM",
    ComponentCategory.SSD: "SSD",
    ComponentCategory.PSU: "PSU",
    ComponentCategory.CASE: "CASE",
    ComponentCategory.COOLER: "COOL",
}

AnyFont = ImageFont.FreeTypeFont | ImageFont.ImageFont
Parts = dict[ComponentCategory, Component]


def load_font(size: int, bold: bool = False) -> AnyFont:
    for path in BOLD_CANDIDATES if bold else FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # Pillow's bitmap fallback: ugly, but the bot must not fall over because a
    # host has no fonts installed.
    return ImageFont.load_default(size)


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: AnyFont, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


#: Drawn along the bottom edge when the caller supplies nothing else. English
#: on purpose: it is the neutral default, never a stray Russian line.
DEFAULT_FOOTER = "AmigoZT PC visualisation · not a product photo · indicative price"


def cache_key(
    title: str,
    parts: Parts,
    price: Decimal | None,
    preset: VisualPreset | None = None,
    *,
    subtitle: str | None = None,
    footer: str | None = None,
) -> str:
    payload = "|".join(
        [
            title,
            *(f"{c.value}={p.id}" for c, p in sorted(parts.items())),
            str(price),
            preset.key if preset else "-",
            # Translated copy is drawn into the pixels, so it belongs in the
            # key: otherwise an English customer would be served the Polish
            # render of the same machine.
            subtitle or "-",
            footer or "-",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _spec(parts: Parts, category: ComponentCategory, expected: type):  # type: ignore[no-untyped-def]
    component = parts.get(category)
    if component is None:
        return None
    spec = component.spec
    return spec if isinstance(spec, expected) else None


def _palette(finish: CaseFinish) -> dict[str, RGB]:
    """Colours for the tower itself, matching the real case finish."""
    if finish is CaseFinish.WHITE:
        return {
            "body": (232, 234, 238),
            "edge": (208, 211, 216),
            "interior": (245, 246, 248),
            "glass": (222, 231, 240),
            "part": (198, 203, 210),
            "part_edge": (170, 176, 184),
            "hub": (214, 218, 224),
        }
    return {
        "body": (34, 38, 45),
        "edge": (52, 57, 66),
        "interior": (26, 30, 36),
        "glass": (40, 48, 58),
        "part": (58, 64, 74),
        "part_edge": (78, 86, 98),
        "hub": (46, 52, 60),
    }


def _dim(colour: RGB, factor: float) -> RGB:
    return tuple(int(channel * factor) for channel in colour)  # type: ignore[return-value]


# --- the machine --------------------------------------------------------------


def draw_pc(
    image: Image.Image, parts: Parts, box: tuple[int, int, int, int], preset: VisualPreset
) -> None:
    """Draw the tower, seen through its side panel, inside ``box``.

    Lighting is painted on a separate layer and blurred, so lit parts glow
    into the interior the way they do behind real glass.
    """
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = box

    case_spec = _spec(parts, ComponentCategory.CASE, CaseSpec)
    cooler_spec = _spec(parts, ComponentCategory.COOLER, CoolerSpec)
    gpu_spec = _spec(parts, ComponentCategory.GPU, GpuSpec)

    palette = _palette(preset.finish)
    colours = preset.colours
    glow = preset.glow

    # Chassis and interior.
    draw.rounded_rectangle([left, top, right, bottom], radius=18, fill=palette["body"])
    draw.rounded_rectangle([left, top, right, bottom], radius=18, outline=palette["edge"], width=3)
    inner = (left + 16, top + 16, right - 16, bottom - 16)
    draw.rounded_rectangle(inner, radius=10, fill=palette["interior"])
    ix0, iy0, ix1, iy1 = inner
    inner_h = iy1 - iy0

    # Glow layer: everything lit is drawn here too, then blurred underneath.
    light = Image.new("RGBA", image.size, (0, 0, 0, 0))
    light_draw = ImageDraw.Draw(light)

    def lit(colour: RGB) -> RGB:
        return colour if glow else _dim(colour, 0.7)

    # Front intake fans down the left edge.
    fan_count = max(2, min(4, case_spec.included_fans if case_spec else 3))
    fan_radius = min(38, inner_h // (fan_count * 2 + 1))
    fan_x = ix0 + fan_radius + 12
    spacing = inner_h / (fan_count + 1)
    for index in range(fan_count):
        cy = iy0 + spacing * (index + 1)
        colour = lit(colours[index % len(colours)])
        ring = [fan_x - fan_radius, cy - fan_radius, fan_x + fan_radius, cy + fan_radius]
        draw.ellipse(ring, outline=colour, width=4)
        if glow:
            light_draw.ellipse(ring, outline=(*colour, 170), width=10)
        hub = fan_radius // 3
        draw.ellipse([fan_x - hub, cy - hub, fan_x + hub, cy + hub], fill=palette["hub"])

    board_x0 = fan_x + fan_radius + 22
    board_x1 = ix1 - 14
    board_y0 = iy0 + 18
    board_y1 = iy1 - 130
    draw.rounded_rectangle([board_x0, board_y0, board_x1, board_y1], radius=8, fill=palette["part"])

    pump_colour = lit(colours[0])

    # AIO radiator across the top, or an air tower on the board.
    if cooler_spec is not None and cooler_spec.cooler_type is CoolerType.AIO:
        rad_h = 30
        draw.rounded_rectangle(
            [board_x0 + 6, iy0 + 6, board_x1 - 6, iy0 + 6 + rad_h],
            radius=6,
            fill=palette["part_edge"],
        )
        # Radiator fans, lit like the intakes.
        rad_fans = 3 if cooler_spec.radiator_mm >= 360 else 2
        rad_w = (board_x1 - board_x0 - 12) / rad_fans
        for index in range(rad_fans):
            cx = board_x0 + 6 + rad_w * (index + 0.5)
            r = min(12, rad_h // 2 - 3)
            colour = lit(colours[(index + 1) % len(colours)])
            draw.ellipse(
                [cx - r, iy0 + 6 + rad_h / 2 - r, cx + r, iy0 + 6 + rad_h / 2 + r],
                outline=colour,
                width=3,
            )

        pump_x0, pump_y0 = board_x0 + 60, board_y0 + 70
        draw.rounded_rectangle(
            [pump_x0, pump_y0, pump_x0 + 78, pump_y0 + 78],
            radius=10,
            fill=palette["part_edge"],
            outline=pump_colour,
            width=4,
        )
        if glow:
            light_draw.rounded_rectangle(
                [pump_x0, pump_y0, pump_x0 + 78, pump_y0 + 78],
                radius=10,
                outline=(*pump_colour, 160),
                width=10,
            )
        for offset in (20, 58):
            draw.line(
                [pump_x0 + offset, pump_y0, pump_x0 + offset, iy0 + 6 + rad_h],
                fill=palette["edge"],
                width=7,
            )
    else:
        tower_x0, tower_y0 = board_x0 + 52, board_y0 + 40
        draw.rounded_rectangle(
            [tower_x0, tower_y0, tower_x0 + 96, tower_y0 + 132], radius=6, fill=palette["part_edge"]
        )
        for offset in range(6):
            fin_y = tower_y0 + 14 + offset * 20
            draw.line(
                [tower_x0 + 8, fin_y, tower_x0 + 88, fin_y], fill=palette["interior"], width=3
            )
        # Tower fan, lit.
        fan_cx, fan_cy, r = tower_x0 + 48, tower_y0 + 66, 30
        draw.ellipse([fan_cx - r, fan_cy - r, fan_cx + r, fan_cy + r], outline=pump_colour, width=3)
        if glow:
            light_draw.ellipse(
                [fan_cx - r, fan_cy - r, fan_cx + r, fan_cy + r],
                outline=(*pump_colour, 140),
                width=8,
            )

    # Memory sticks right of the cooler; lit in gaming style.
    ram_x = board_x1 - 58
    for index in range(2):
        stick_x = ram_x + index * 20
        colour = lit(colours[(index + 2) % len(colours)]) if glow else palette["part_edge"]
        draw.rounded_rectangle(
            [stick_x, board_y0 + 30, stick_x + 12, board_y0 + 150], radius=4, fill=colour
        )
        if glow:
            light_draw.rounded_rectangle(
                [stick_x, board_y0 + 30, stick_x + 12, board_y0 + 150],
                radius=4,
                fill=(*colour, 120),
            )

    # Graphics card: width tracks the real length of the card.
    if gpu_spec is not None:
        ratio = min(1.0, gpu_spec.length_mm / 400)
        gpu_w = int((board_x1 - board_x0 - 20) * max(0.55, ratio))
        gpu_y = board_y1 - 96
        draw.rounded_rectangle(
            [board_x0 + 10, gpu_y, board_x0 + 10 + gpu_w, gpu_y + 62],
            radius=8,
            fill=palette["part_edge"],
            outline=palette["edge"],
            width=2,
        )
        for index in range(2):
            cx = board_x0 + 60 + index * 90
            if cx + 26 < board_x0 + 10 + gpu_w:
                draw.ellipse(
                    [cx - 26, gpu_y + 8, cx + 26, gpu_y + 54], outline=palette["interior"], width=3
                )
        if glow:
            # Accent strip along the top edge of the card - the usual RGB bar.
            strip = colours[3 % len(colours)] if len(colours) > 3 else colours[0]
            draw.line(
                [board_x0 + 14, gpu_y + 3, board_x0 + 6 + gpu_w, gpu_y + 3], fill=strip, width=4
            )
            light_draw.line(
                [board_x0 + 14, gpu_y + 3, board_x0 + 6 + gpu_w, gpu_y + 3],
                fill=(*strip, 160),
                width=12,
            )

    # PSU shroud along the bottom.
    draw.rounded_rectangle([ix0 + 10, iy1 - 96, ix1 - 14, iy1 - 20], radius=8, fill=palette["part"])
    draw.text((ix0 + 26, iy1 - 74), "PSU", font=load_font(20, bold=True), fill=palette["interior"])

    # Composite the glow under the outlines, then the glass edge on top.
    if glow:
        blurred = light.filter(ImageFilter.GaussianBlur(14))
        image.paste(Image.alpha_composite(image.convert("RGBA"), blurred).convert("RGB"))
        draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(inner, radius=10, outline=palette["glass"], width=5)


# --- the card -----------------------------------------------------------------


def render_build_image(
    title: str,
    parts: Parts,
    price_pln: Decimal | None,
    *,
    subtitle: str | None = None,
    preset: VisualPreset | None = None,
    footer: str | None = None,
    output_dir: Path,
) -> Path:
    """Draw the card and return its path, reusing an identical earlier render."""
    chosen = preset or default_preset(parts)
    caption = footer or DEFAULT_FOOTER
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (
        "build-"
        + cache_key(title, parts, price_pln, chosen, subtitle=subtitle, footer=caption)
        + ".png"
    )
    if path.exists():
        return path

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    brand_font = load_font(26, bold=True)
    title_font = load_font(46, bold=True)
    subtitle_font = load_font(24)
    label_font = load_font(20, bold=True)
    part_font = load_font(24)
    price_font = load_font(62, bold=True)
    footer_font = load_font(20)

    draw.text((MARGIN, MARGIN - 14), "AMIGOZT PC", font=brand_font, fill=ACCENT)

    y = MARGIN + 22
    draw.text(
        (MARGIN, y),
        fit_text(draw, title, title_font, WIDTH - 2 * MARGIN),
        font=title_font,
        fill=TEXT,
    )
    y += 60

    if subtitle:
        draw.text(
            (MARGIN, y),
            fit_text(draw, subtitle, subtitle_font, WIDTH - 2 * MARGIN),
            font=subtitle_font,
            fill=MUTED,
        )
        y += 38

    y += 8
    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill=PANEL, width=3)
    y += 22

    draw_pc(image, parts, (MARGIN, y, MARGIN + 380, HEIGHT - 190), chosen)
    draw = ImageDraw.Draw(image)

    list_x = MARGIN + 420
    list_width = WIDTH - MARGIN - list_x
    row_y = y + 4
    # Chip (34px) + name (24px) + breathing room; anything tighter overlaps.
    row_height = 76
    label_width = 78

    for category in PC_CATEGORIES:
        component = parts.get(category)
        if component is None:
            continue
        draw.rounded_rectangle(
            [(list_x, row_y), (list_x + label_width, row_y + 34)], radius=8, fill=PANEL
        )
        draw.text(
            (list_x + 10, row_y + 6),
            CATEGORY_LABELS.get(category, category.value.upper()[:4]),
            font=label_font,
            fill=ACCENT,
        )
        draw.text(
            (list_x, row_y + 40),
            fit_text(draw, component.name, part_font, list_width),
            font=part_font,
            fill=TEXT,
        )
        row_y += row_height

    if price_pln is not None:
        box_top = HEIGHT - MARGIN - 128
        draw.rounded_rectangle(
            [(MARGIN, box_top), (WIDTH - MARGIN, box_top + 96)], radius=14, fill=PANEL
        )
        draw.text((MARGIN + 24, box_top + 14), "TOTAL", font=label_font, fill=MUTED)
        draw.text(
            (MARGIN + 24, box_top + 34),
            format_price_pln(price_pln),
            font=price_font,
            fill=PRICE_GREEN,
        )

    # Preset name in the corner so the customer knows which look they picked.
    style_text = chosen.title
    draw.text(
        (WIDTH - MARGIN - draw.textlength(style_text, font=footer_font), MARGIN - 10),
        style_text,
        font=footer_font,
        fill=MUTED,
    )

    draw.text(
        (MARGIN, HEIGHT - MARGIN - 6),
        fit_text(draw, caption, footer_font, WIDTH - 2 * MARGIN),
        font=footer_font,
        fill=MUTED,
    )

    image.save(path, format="PNG", optimize=True)
    logger.debug("Rendered build image %s", path.name)
    return path


#: Thumbnail of just the machine, for grids of variants. Portrait, in the
#: proportions the tower is drawn at on the full card - a square box makes
#: draw_pc overflow and clips the front fans.
THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT = 440, 660


def render_build_thumbnail(
    parts: Parts, preset: VisualPreset | None = None, *, output_dir: Path
) -> Path:
    """Draw only the tower, square, for a tile in a grid.

    The full card carries a parts list and a price, which are unreadable once
    scaled into a tile - and redundant, because the tile prints them itself.
    """
    chosen = preset or default_preset(parts)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = "|".join(
        [
            "thumb",
            *(f"{c.value}={p.id}" for c, p in sorted(parts.items())),
            chosen.key,
            f"{THUMBNAIL_WIDTH}x{THUMBNAIL_HEIGHT}",
        ]
    )
    path = output_dir / f"pc-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}.png"
    if path.exists():
        return path

    image = Image.new("RGB", (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), BACKGROUND)
    margin = 24
    box = (margin, margin, THUMBNAIL_WIDTH - margin, THUMBNAIL_HEIGHT - margin)
    draw_pc(image, parts, box, chosen)
    image.save(path, format="PNG", optimize=True)
    return path
