"""Domain enumerations.

These are storage- and transport-independent: they are used by the Telegram
layer, by the (future) compatibility engine and by the database layer alike.
Values are stable strings because they are persisted in JSON columns.
"""

from __future__ import annotations

from enum import StrEnum


class Purpose(StrEnum):
    GAMING = "gaming"
    GAMING_STREAMING = "gaming_streaming"
    WORK = "work"
    DESIGN = "design"
    AI_ML = "ai_ml"
    WORKSTATION = "workstation"
    UNIVERSAL = "universal"

    @property
    def is_gaming(self) -> bool:
        return self in {Purpose.GAMING, Purpose.GAMING_STREAMING, Purpose.UNIVERSAL}


class Resolution(StrEnum):
    FHD = "1080p"
    QHD = "1440p"
    UHD = "4k"

    @property
    def pixels(self) -> int:
        return {"1080p": 1920 * 1080, "1440p": 2560 * 1440, "4k": 3840 * 2160}[self.value]


class TargetFps(StrEnum):
    FPS_60 = "60"
    FPS_100 = "100"
    FPS_144 = "144"
    FPS_165 = "165"
    FPS_240 = "240"
    FPS_300_PLUS = "300+"
    FPS_500_PLUS = "500+"
    FPS_700_PLUS = "700+"

    @property
    def numeric(self) -> int:
        return int(self.value.rstrip("+"))


class Priority(StrEnum):
    """What the customer cares about. Several may be chosen at once."""

    MAX_FPS = "max_fps"
    PRICE_PERFORMANCE = "price_performance"
    SILENCE = "silence"
    COOLING = "cooling"
    LOOKS = "looks"
    VERSATILITY = "versatility"
    EFFICIENCY = "efficiency"
    COMPACT = "compact"
    UPGRADEABILITY = "upgradeability"


#: Order shown in the picker: the two most-asked-for first.
PRIORITY_ORDER: tuple[Priority, ...] = (
    Priority.MAX_FPS,
    Priority.PRICE_PERFORMANCE,
    Priority.SILENCE,
    Priority.COOLING,
    Priority.LOOKS,
    Priority.COMPACT,
    Priority.EFFICIENCY,
    Priority.UPGRADEABILITY,
    Priority.VERSATILITY,
)

#: How many priorities one customer may tick. More than this stops meaning
#: anything to the generator - everything becomes "important".
MAX_PRIORITIES = 4


class Aesthetics(StrEnum):
    BLACK = "black"
    WHITE = "white"
    BLACK_RGB = "black_rgb"
    WHITE_RGB = "white_rgb"
    MINIMAL = "minimal"
    GAMING = "gaming"

    @property
    def wants_rgb(self) -> bool:
        return self in {Aesthetics.BLACK_RGB, Aesthetics.WHITE_RGB, Aesthetics.GAMING}

    @property
    def is_white(self) -> bool:
        return self in {Aesthetics.WHITE, Aesthetics.WHITE_RGB}


class CpuBrand(StrEnum):
    ANY = "any"
    AMD = "amd"
    INTEL = "intel"


class GpuBrand(StrEnum):
    ANY = "any"
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"


class BuildTier(StrEnum):
    BUDGET = "budget"
    OPTIMAL = "optimal"
    PERFORMANCE = "performance"


class AutoOr(StrEnum):
    """Sentinel used by steps where the user may delegate the choice to us."""

    AUTO = "auto"


# --- Games offered in the configurator -------------------------------------
# Key -> display name. Free-text entries are stored as-is.
KNOWN_GAMES: dict[str, str] = {
    "cs2": "CS2",
    "fortnite": "Fortnite",
    "gta5": "GTA V",
    "gta6": "GTA VI",
    "cyberpunk": "Cyberpunk 2077",
    "warzone": "Warzone",
    "valorant": "Valorant",
    "minecraft": "Minecraft",
    "apex": "Apex Legends",
    "pubg": "PUBG",
    "rdr2": "Red Dead Redemption 2",
    "diablo4": "Diablo IV",
    "wow": "World of Warcraft",
}

#: Short labels for inline buttons. Full titles would be clipped on narrow
#: phones, so the keyboard shows these while cards keep ``KNOWN_GAMES``.
GAME_BUTTON_LABELS: dict[str, str] = {
    "cyberpunk": "Cyberpunk",
    "apex": "Apex",
    "rdr2": "RDR 2",
    "wow": "WoW",
}


def game_button_label(key: str) -> str:
    return GAME_BUTTON_LABELS.get(key) or KNOWN_GAMES.get(key, key)


BUDGET_PRESETS_PLN: tuple[int, ...] = (2500, 3000, 3500, 4000, 5000, 6000, 7000, 8000, 10000)

MIN_BUDGET_PLN = 1800
MAX_BUDGET_PLN = 60000

STORAGE_PRESETS_GB: tuple[int, ...] = (500, 1000, 2000, 4000)
RAM_PRESETS_GB: tuple[int, ...] = (16, 32, 64, 96, 128)


class LeadStatus(StrEnum):
    """Lifecycle of a purchase request."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    CONTACTED = "contacted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def is_open(self) -> bool:
        return self in {LeadStatus.NEW, LeadStatus.IN_PROGRESS, LeadStatus.CONTACTED}


#: Badge shown next to a lead in the admin interface.
LEAD_STATUS_BADGES: dict[LeadStatus, str] = {
    LeadStatus.NEW: "🆕",
    LeadStatus.IN_PROGRESS: "🔧",
    LeadStatus.CONTACTED: "📞",
    LeadStatus.COMPLETED: "✅",
    LeadStatus.CANCELLED: "❌",
}
