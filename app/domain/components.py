"""Component catalogue domain model.

Storage- and transport-independent. Every category has its own typed spec, so
the compatibility engine reads real fields (``socket``, ``max_gpu_length_mm``)
instead of poking at an untyped dict, and a malformed catalogue entry fails at
load time rather than halfway through building a customer's PC.

Two kinds of field live on a spec:

* the original, *required* ones (socket, lengths, wattage) - a catalogue entry
  without them is rejected;
* the compatibility-detail fields added for the physical build check
  (radiator positions, ARGB headers, PSU form factor ...). These are
  ``Optional`` and default to ``None``, which the engine reads as **UNKNOWN**:
  never "fine", never "broken". Nobody filling in the catalogue is ever forced
  to invent a number to make a file load.

Every component also carries provenance (``spec_source``, ``spec_checked_at``,
``spec_verified``) so an admin can tell a manufacturer-confirmed dimension
from one typed in from memory.

A note on ``performance_index``: it is AmigoZT's own coarse relative rating
used to rank parts inside a budget. It is NOT a benchmark score and must never
be presented to a user as one. Frame rates come from ``app.services.benchmarks``
and only ever from recorded measurements.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentCategory(StrEnum):
    # --- PC parts ---
    CPU = "cpu"
    GPU = "gpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    SSD = "ssd"
    PSU = "psu"
    CASE = "case"
    COOLER = "cooler"
    FANS = "fans"
    # --- peripherals and furniture ---
    MONITOR = "monitor"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    HEADSET = "headset"
    MICROPHONE = "microphone"
    WEBCAM = "webcam"
    SPEAKERS = "speakers"
    MOUSEPAD = "mousepad"
    DESK = "desk"
    CHAIR = "chair"
    LIGHTING = "lighting"
    # --- misc ---
    WIFI_ADAPTER = "wifi_adapter"
    BLUETOOTH_ADAPTER = "bluetooth_adapter"
    OPERATING_SYSTEM = "operating_system"
    OTHER = "other"


#: Categories that make up a desktop PC, in the order a build card lists them.
PC_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CPU,
    ComponentCategory.COOLER,
    ComponentCategory.MOTHERBOARD,
    ComponentCategory.RAM,
    ComponentCategory.GPU,
    ComponentCategory.SSD,
    ComponentCategory.PSU,
    ComponentCategory.CASE,
)

#: Parts every build must contain to be sellable.
REQUIRED_CATEGORIES: frozenset[ComponentCategory] = frozenset(
    {
        ComponentCategory.CPU,
        ComponentCategory.MOTHERBOARD,
        ComponentCategory.RAM,
        ComponentCategory.SSD,
        ComponentCategory.PSU,
        ComponentCategory.CASE,
    }
)

ACCESSORY_CATEGORIES: frozenset[ComponentCategory] = frozenset(
    {
        ComponentCategory.MONITOR,
        ComponentCategory.KEYBOARD,
        ComponentCategory.MOUSE,
        ComponentCategory.HEADSET,
        ComponentCategory.MICROPHONE,
        ComponentCategory.WEBCAM,
        ComponentCategory.SPEAKERS,
        ComponentCategory.MOUSEPAD,
        ComponentCategory.DESK,
        ComponentCategory.CHAIR,
        ComponentCategory.LIGHTING,
    }
)


class Socket(StrEnum):
    AM4 = "AM4"
    AM5 = "AM5"
    LGA1700 = "LGA1700"
    LGA1851 = "LGA1851"


class MemoryType(StrEnum):
    DDR4 = "DDR4"
    DDR5 = "DDR5"


class FormFactor(StrEnum):
    ATX = "ATX"
    MICRO_ATX = "mATX"
    MINI_ITX = "ITX"
    E_ATX = "E-ATX"


class CoolerType(StrEnum):
    AIR = "air"
    AIO = "aio"


class Colour(StrEnum):
    BLACK = "black"
    WHITE = "white"
    OTHER = "other"


class PsuFormFactor(StrEnum):
    ATX = "ATX"
    SFX = "SFX"
    SFX_L = "SFX-L"
    TFX = "TFX"


class Position(StrEnum):
    """Where a fan or radiator mounts inside a case."""

    FRONT = "front"
    TOP = "top"
    REAR = "rear"
    BOTTOM = "bottom"
    SIDE = "side"


class ArgbConnector(StrEnum):
    """Lighting connector a part needs from the motherboard.

    5 V 3-pin addressable and 12 V 4-pin RGB are electrically different and
    must never be treated as interchangeable. ``OWN_CONTROLLER`` means the
    part ships with its own hub/controller and needs no header at all.
    """

    ARGB_5V = "5v_3pin"
    RGB_12V = "12v_4pin"
    OWN_CONTROLLER = "own_controller"
    NONE = "none"


class FanConnector(StrEnum):
    PWM_4PIN = "4pin_pwm"
    DC_3PIN = "3pin_dc"


class MemoryProfile(StrEnum):
    EXPO = "EXPO"
    XMP = "XMP"


class CpuSupport(StrEnum):
    """How a motherboard supports a CPU family, per the vendor's CPU list."""

    NATIVE = "native"
    BIOS_UPDATE = "bios_update_required"
    UNSUPPORTED = "unsupported"


# --- shared sub-models --------------------------------------------------------


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FanMount(_Spec):
    """Fan positions available at one location of a case."""

    count: int = Field(ge=0)
    sizes_mm: list[int] = Field(default_factory=list)


class DisplayPorts(_Spec):
    """Video connectors on a GPU (outputs) or a monitor (inputs)."""

    hdmi: int = Field(default=0, ge=0)
    hdmi_version: str | None = None
    displayport: int = Field(default=0, ge=0)
    displayport_version: str | None = None


# --- specs --------------------------------------------------------------------


class CpuSpec(_Spec):
    kind: Literal[ComponentCategory.CPU] = ComponentCategory.CPU
    socket: Socket
    cores: int = Field(ge=1)
    threads: int = Field(ge=1)
    tdp_w: int = Field(ge=1)
    #: Power the cooler must actually dissipate under sustained load.
    max_power_w: int = Field(ge=1)
    memory_types: list[MemoryType] = Field(min_length=1)
    max_memory_speed_mhz: int = Field(ge=1600)
    integrated_graphics: bool = False
    includes_cooler: bool = False
    performance_index: int = Field(ge=1, le=1000)
    gaming_index: int = Field(ge=1, le=1000)
    #: Vendor family key used against ``MotherboardSpec.cpu_support``
    #: (``ryzen_7000``, ``core_14th`` ...). None = unknown.
    family: str | None = None


class GpuSpec(_Spec):
    kind: Literal[ComponentCategory.GPU] = ComponentCategory.GPU
    vram_gb: int = Field(ge=1)
    tdp_w: int = Field(ge=1)
    recommended_psu_w: int = Field(ge=1)
    length_mm: int = Field(ge=1)
    slots: float = Field(ge=1)
    pcie_8pin: int = Field(default=0, ge=0)
    pcie_12vhpwr: int = Field(default=0, ge=0)
    performance_index: int = Field(ge=1, le=1000)
    ray_tracing: bool = False
    upscaling: list[str] = Field(default_factory=list)
    # --- compatibility detail (None = unknown) ---
    height_mm: int | None = Field(default=None, ge=1)
    width_mm: int | None = Field(default=None, ge=1)
    outputs: DisplayPorts | None = None
    #: Whether a 12VHPWR/12V-2x6 adapter ships in the box.
    adapter_included: bool | None = None


class MotherboardSpec(_Spec):
    kind: Literal[ComponentCategory.MOTHERBOARD] = ComponentCategory.MOTHERBOARD
    socket: Socket
    chipset: str
    form_factor: FormFactor
    memory_type: MemoryType
    memory_slots: int = Field(ge=2)
    max_memory_gb: int = Field(ge=8)
    max_memory_speed_mhz: int = Field(ge=1600)
    m2_slots: int = Field(ge=0)
    pcie_version: int = Field(ge=3, le=5)
    wifi: bool = False
    bluetooth: bool = False
    # --- compatibility detail (None = unknown) ---
    #: Per M.2 slot, e.g. ["2280", "2280", "22110"].
    m2_slot_sizes: list[str] | None = None
    #: Per M.2 slot PCIe generation, e.g. [5, 4, 4].
    m2_slot_gens: list[int] | None = None
    sata_ports: int | None = Field(default=None, ge=0)
    argb_5v_headers: int | None = Field(default=None, ge=0)
    rgb_12v_headers: int | None = Field(default=None, ge=0)
    #: All 4-pin fan/pump headers, CPU_FAN included.
    fan_headers: int | None = Field(default=None, ge=0)
    usb_c_header: bool | None = None
    #: CPU family key -> support level, from the vendor's CPU support list.
    cpu_support: dict[str, CpuSupport] | None = None
    bios_flashback: bool | None = None
    memory_profiles: list[MemoryProfile] | None = None
    #: Bandwidth-sharing caveats from the manual ("M2_3 disables SATA 5/6").
    lane_sharing_notes: list[str] | None = None


class RamSpec(_Spec):
    kind: Literal[ComponentCategory.RAM] = ComponentCategory.RAM
    memory_type: MemoryType
    total_capacity_gb: int = Field(ge=4)
    modules: int = Field(ge=1)
    speed_mhz: int = Field(ge=1600)
    cas_latency: int = Field(ge=10)
    height_mm: int = Field(ge=15)
    rgb: bool = False
    # --- compatibility detail (None = unknown) ---
    profiles: list[MemoryProfile] | None = None
    argb_connector: ArgbConnector | None = None


class SsdSpec(_Spec):
    kind: Literal[ComponentCategory.SSD] = ComponentCategory.SSD
    capacity_gb: int = Field(ge=120)
    interface: str
    pcie_generation: int = Field(ge=3, le=5)
    read_mb_s: int = Field(ge=100)
    write_mb_s: int = Field(ge=100)
    # --- compatibility detail (None = unknown) ---
    #: "M.2 2280", "M.2 2230", "2.5 SATA", "3.5 HDD".
    form_factor: str | None = None
    heatsink: bool | None = None


class PsuSpec(_Spec):
    kind: Literal[ComponentCategory.PSU] = ComponentCategory.PSU
    wattage: int = Field(ge=300)
    efficiency: str
    modular: str
    atx_version: str
    pcie_8pin: int = Field(default=0, ge=0)
    pcie_12vhpwr: int = Field(default=0, ge=0)
    eps_8pin: int = Field(default=1, ge=1)
    length_mm: int = Field(ge=100)
    # --- compatibility detail (None = unknown) ---
    form_factor: PsuFormFactor | None = None


class CaseSpec(_Spec):
    kind: Literal[ComponentCategory.CASE] = ComponentCategory.CASE
    form_factors: list[FormFactor] = Field(min_length=1)
    max_gpu_length_mm: int = Field(ge=100)
    max_cooler_height_mm: int = Field(ge=30)
    max_psu_length_mm: int = Field(ge=100)
    #: Radiator sizes the case takes anywhere. ``radiator_positions`` is the
    #: precise version; this list stays for the original rule set.
    radiator_support_mm: list[int] = Field(default_factory=list)
    colour: Colour = Colour.BLACK
    rgb: bool = False
    included_fans: int = Field(default=0, ge=0)
    # --- compatibility detail (None = unknown) ---
    psu_form_factors: list[PsuFormFactor] | None = None
    max_gpu_slots: float | None = Field(default=None, ge=1)
    #: GPU clearance once a radiator sits in the front.
    max_gpu_length_with_front_radiator_mm: int | None = Field(default=None, ge=50)
    radiator_positions: dict[Position, list[int]] | None = None
    fan_mounts: dict[Position, FanMount] | None = None
    max_fans: int | None = Field(default=None, ge=0)
    included_fan_size_mm: int | None = Field(default=None, ge=40)
    drive_bays_25: int | None = Field(default=None, ge=0)
    drive_bays_35: int | None = Field(default=None, ge=0)
    front_usb_c: bool | None = None
    #: What the case's own lighting (fans, strips) plugs into.
    argb_connector: ArgbConnector | None = None
    side_panel: str | None = None


class CoolerSpec(_Spec):
    kind: Literal[ComponentCategory.COOLER] = ComponentCategory.COOLER
    cooler_type: CoolerType
    sockets: list[Socket] = Field(min_length=1)
    tdp_rating_w: int = Field(ge=30)
    height_mm: int = Field(default=0, ge=0)
    radiator_mm: int = Field(default=0, ge=0)
    ram_clearance_mm: int = Field(default=0, ge=0)
    colour: Colour = Colour.BLACK
    rgb: bool = False
    # --- compatibility detail (None = unknown) ---
    radiator_thickness_mm: int | None = Field(default=None, ge=10)
    fan_thickness_mm: int | None = Field(default=None, ge=10)
    fans: int | None = Field(default=None, ge=0)
    argb_connector: ArgbConnector | None = None


class FanSpec(_Spec):
    """A pack of case fans."""

    kind: Literal[ComponentCategory.FANS] = ComponentCategory.FANS
    size_mm: int = Field(ge=40)
    count: int = Field(ge=1)
    thickness_mm: int | None = Field(default=None, ge=10)
    connector: FanConnector | None = None
    argb_connector: ArgbConnector | None = None
    rgb: bool = False
    colour: Colour = Colour.BLACK


class MonitorSpec(_Spec):
    """Monitors get a real spec because a build's resolution and frame-rate
    target only mean something paired with a matching screen."""

    kind: Literal[ComponentCategory.MONITOR] = ComponentCategory.MONITOR
    size_inch: float = Field(ge=10, le=60)
    resolution: str
    refresh_hz: int = Field(ge=50, le=1000)
    panel: str
    #: OLED panels really do quote 0.03 ms, so the floor is set by physics
    #: rather than by what LCDs could manage when this was written.
    response_ms: float = Field(ge=0.01, le=20)
    adaptive_sync: bool = False
    curved: bool = False
    colour: Colour = Colour.BLACK
    # --- compatibility detail (None = unknown) ---
    inputs: DisplayPorts | None = None


class PeripheralSpec(_Spec):
    """Shared shape for input devices, audio and furniture.

    These have no compatibility rules to enforce, so the fields are
    descriptive: enough to render a useful card and to match a customer's
    stated style, not a pretend engineering model.
    """

    kind: Literal[
        ComponentCategory.KEYBOARD,
        ComponentCategory.MOUSE,
        ComponentCategory.HEADSET,
        ComponentCategory.MICROPHONE,
        ComponentCategory.WEBCAM,
        ComponentCategory.SPEAKERS,
        ComponentCategory.MOUSEPAD,
        ComponentCategory.DESK,
        ComponentCategory.CHAIR,
        ComponentCategory.LIGHTING,
    ]
    summary: str
    wireless: bool = False
    rgb: bool = False
    colour: Colour = Colour.BLACK
    #: Free-form highlights shown on the card, e.g. "60 g", "Hot-swap".
    highlights: list[str] = Field(default_factory=list)


class GenericSpec(_Spec):
    """Fallback for categories with no compatibility rules yet."""

    model_config = ConfigDict(extra="allow")

    kind: Literal[
        ComponentCategory.WIFI_ADAPTER,
        ComponentCategory.BLUETOOTH_ADAPTER,
        ComponentCategory.OPERATING_SYSTEM,
        ComponentCategory.OTHER,
    ]


ComponentSpec = Annotated[
    CpuSpec
    | GpuSpec
    | MotherboardSpec
    | RamSpec
    | SsdSpec
    | PsuSpec
    | CaseSpec
    | CoolerSpec
    | FanSpec
    | MonitorSpec
    | PeripheralSpec
    | GenericSpec,
    Field(discriminator="kind"),
]


# --- component ----------------------------------------------------------------


class Component(BaseModel):
    """One catalogue entry."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9\-]+$")
    category: ComponentCategory
    brand: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    spec: ComponentSpec

    #: Indicative price used for ranking and for an estimate when no live offer
    #: exists. The authoritative number always comes from ``ProductOffer``.
    reference_price_pln: Decimal | None = None

    product_url: str | None = None
    #: A real photo of *this exact model*, or None. Never a guessed URL.
    image_url: str | None = None
    #: Where the photo comes from (manufacturer / retailer name), when it was
    #: checked, and whether someone confirmed it shows the exact model.
    image_source: str | None = None
    image_checked_at: date | None = None
    image_verified: bool = False
    discontinued: bool = False

    #: Where the spec numbers came from (manufacturer page URL), when they
    #: were checked, and whether someone confirmed them against that source.
    #: Unverified specs still drive the engine, but every check built on them
    #: is reported to the admin as "not verified".
    spec_source: str | None = None
    spec_checked_at: date | None = None
    spec_verified: bool = False
    #: Caveats about the numbers above that an admin must read before buying:
    #: "GPU 432 mm only with the HDD cage removed", "TDP rating is the
    #: retailer's figure, the manufacturer publishes none".
    spec_notes: list[str] = Field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model}"

    @property
    def short_name(self) -> str:
        """Trimmed name for inline buttons and narrow screens."""
        return self.model if len(self.model) >= 8 else self.name

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return self.name


def parse_component(payload: dict[str, Any]) -> Component:
    """Build a ``Component`` from a catalogue record.

    The spec discriminator is derived from the category so that seed files do
    not have to repeat it.
    """
    data = dict(payload)
    spec = dict(data.get("spec") or {})
    spec.setdefault("kind", data.get("category"))
    data["spec"] = spec
    return Component(**data)
