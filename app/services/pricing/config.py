"""Commercial pricing configuration, loaded from ``app/data/pricing/margins.json``.

Everything a shop owner might want to tune - margin ranges per category,
minimum profit bands, order profit goals, assembly tiers, operating costs,
rounding - lives in that file. Changing the business model must never mean
editing pricing logic.
"""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.components import ComponentCategory
from app.services.pricing.complexity import ComplexityLevel

DEFAULT_CONFIG_FILE = Path(__file__).resolve().parents[2] / "data" / "pricing" / "margins.json"


class MarginRange(BaseModel):
    """Mark-up range for a category, in percent."""

    model_config = ConfigDict(frozen=True)

    low: Decimal = Field(ge=0, le=100)
    high: Decimal = Field(ge=0, le=100)

    @field_validator("high")
    @classmethod
    def _ordered(cls, high: Decimal, info) -> Decimal:  # type: ignore[no-untyped-def]
        low = info.data.get("low")
        if low is not None and high < low:
            raise ValueError("margin range high must be >= low")
        return high

    def at(self, position: Decimal) -> Decimal:
        """Percent at ``position`` ∈ [0, 1] between low and high."""
        clamped = max(Decimal(0), min(Decimal(1), position))
        return (self.low + (self.high - self.low) * clamped).quantize(Decimal("0.01"))


class ProfitBand(BaseModel):
    """Minimum absolute profit for items priced up to ``up_to_pln``."""

    model_config = ConfigDict(frozen=True)

    up_to_pln: Decimal | None
    min_profit_pln: Decimal = Field(ge=0)


class ProfitGoals(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum_order_profit_pln: Decimal = Field(ge=0)
    target_order_profit_pln: Decimal = Field(ge=0)
    good_order_profit_pln: Decimal = Field(ge=0)


class ProfitTier(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    emoji: str
    from_pln: Decimal

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"


class AssemblyTier(BaseModel):
    """A paid assembly service level. ``includes`` is shown to the customer,
    so it must list only work that is actually performed."""

    model_config = ConfigDict(frozen=True)

    name: str
    fee_pln: Decimal = Field(ge=0)
    includes: tuple[str, ...] = ()


class AssemblyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    by_complexity: dict[str, str]
    tiers: dict[str, AssemblyTier]

    @property
    def order(self) -> list[str]:
        """Tier keys from cheapest to most expensive."""
        return sorted(self.tiers, key=lambda key: self.tiers[key].fee_pln)


class OperatingCosts(BaseModel):
    model_config = ConfigDict(frozen=True)

    fixed_pln: Decimal = Field(default=Decimal(0), ge=0)
    percent_of_price: Decimal = Field(default=Decimal(0), ge=0, le=100)

    def estimate(self, customer_price_pln: Decimal) -> Decimal:
        return (self.fixed_pln + customer_price_pln * self.percent_of_price / 100).quantize(
            Decimal("0.01")
        )


class PricingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    default_margin_range: MarginRange
    category_margin_range: dict[str, MarginRange]
    bands: tuple[ProfitBand, ...]
    profit: ProfitGoals
    profit_tiers: tuple[ProfitTier, ...]
    assembly: AssemblyConfig
    other_services: dict[str, Decimal] = Field(default_factory=dict)
    operating_costs: OperatingCosts = OperatingCosts()
    rounding_step_pln: int = Field(default=50, gt=0)
    competitiveness_warn_percent: Decimal = Field(default=Decimal(5), ge=0)

    # --- margins --------------------------------------------------------

    def margin_range_for(self, category: ComponentCategory | str) -> MarginRange:
        key = category.value if isinstance(category, ComponentCategory) else str(category)
        return self.category_margin_range.get(key, self.default_margin_range)

    def margin_percent_for(
        self, category: ComponentCategory | str, position: Decimal = Decimal(0)
    ) -> Decimal:
        return self.margin_range_for(category).at(position)

    def min_profit_for(self, market_price_pln: Decimal) -> Decimal:
        for band in self.bands:
            if band.up_to_pln is None or market_price_pln <= band.up_to_pln:
                return band.min_profit_pln
        return self.bands[-1].min_profit_pln

    # --- profit ---------------------------------------------------------

    @property
    def minimum_build_profit_pln(self) -> Decimal:
        return self.profit.minimum_order_profit_pln

    def profit_tier_for(self, gross_profit_pln: Decimal) -> ProfitTier:
        tiers = sorted(self.profit_tiers, key=lambda tier: tier.from_pln)
        chosen = tiers[0]
        for tier in tiers:
            if gross_profit_pln >= tier.from_pln:
                chosen = tier
        return chosen

    # --- assembly -------------------------------------------------------

    def assembly_key_for(self, level: ComplexityLevel) -> str:
        key = self.assembly.by_complexity.get(level.value)
        if key is not None and key in self.assembly.tiers:
            return key
        return self.assembly.order[0]

    def assembly_tier(self, key: str) -> AssemblyTier:
        return self.assembly.tiers[key]

    def next_assembly_key(self, key: str) -> str | None:
        order = self.assembly.order
        index = order.index(key) if key in order else -1
        return order[index + 1] if 0 <= index < len(order) - 1 else None

    #: Backwards-compatible name used by earlier call sites.
    def service_tier_for(self, level: ComplexityLevel) -> AssemblyTier:
        return self.assembly_tier(self.assembly_key_for(level))

    def as_snapshot(self) -> dict:
        return {
            "category_margin_range": {
                key: [str(rng.low), str(rng.high)]
                for key, rng in self.category_margin_range.items()
            },
            "bands": [
                {
                    "up_to_pln": str(band.up_to_pln) if band.up_to_pln is not None else None,
                    "min_profit_pln": str(band.min_profit_pln),
                }
                for band in self.bands
            ],
            "profit": {
                "minimum": str(self.profit.minimum_order_profit_pln),
                "target": str(self.profit.target_order_profit_pln),
                "good": str(self.profit.good_order_profit_pln),
            },
            "assembly": {
                key: {"name": tier.name, "fee_pln": str(tier.fee_pln)}
                for key, tier in self.assembly.tiers.items()
            },
            "operating_costs": {
                "fixed_pln": str(self.operating_costs.fixed_pln),
                "percent_of_price": str(self.operating_costs.percent_of_price),
            },
            "rounding_step_pln": self.rounding_step_pln,
        }


def _range(raw: object) -> dict:
    if isinstance(raw, list | tuple) and len(raw) == 2:
        return {"low": raw[0], "high": raw[1]}
    if isinstance(raw, dict):
        return raw
    # A bare number is a fixed margin: both ends equal.
    return {"low": raw, "high": raw}


def load_pricing_config(path: Path | None = None) -> PricingConfig:
    raw = json.loads((path or DEFAULT_CONFIG_FILE).read_text(encoding="utf-8"))
    raw.pop("_meta", None)
    raw["default_margin_range"] = _range(raw.get("default_margin_range", [10, 15]))
    raw["category_margin_range"] = {
        key: _range(value) for key, value in raw.get("category_margin_range", {}).items()
    }
    return PricingConfig(**raw)


@lru_cache(maxsize=1)
def get_pricing_config() -> PricingConfig:
    """Process-wide config. Restart the bot after editing the JSON."""
    return load_pricing_config()
