"""Ties requirements, catalogue, compatibility and commercial pricing together.

This is the single entry point the Telegram layer uses: give it what the
customer asked for, get back priced, compatibility-checked options.

Money model: the customer's budget is what they pay. Working backwards from it
to a component budget is an estimate - the real price depends on per-part
margins, the service tier and rounding - so every candidate is priced exactly
afterwards and anything over budget is dropped.

``BuildOption.client_price_pln`` is customer-facing. ``BuildOption.quote``
carries market cost, profit and hours, and belongs to the admin side only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.config import Settings, get_settings
from app.domain.enums import BuildTier, Priority
from app.domain.lighting import LightingPlan, plan_lighting
from app.domain.requirements import BuildRequirements
from app.services.catalog import Catalog, get_catalog
from app.services.compatibility import CompatibilityReport
from app.services.pricing import (
    CommercialQuote,
    MarketPriceService,
    PricingConfig,
    PricingPolicy,
    get_pricing_config,
)
from app.services.pricing import quote as price_quote
from app.services.recommendation.generator import (
    Parts,
    PriceBook,
    generate_variants,
    minimum_acquisition_cost,
)

logger = logging.getLogger(__name__)

#: Rough share of a build's component cost that ends up as margin once the
#: optimiser has moved categories up their ranges towards target profit.
#: Used only to guess a component budget before the parts are known; the
#: exact price is computed per candidate afterwards.
ASSUMED_MARGIN_PERCENT = Decimal(11)
#: Standard assembly fee plus rounding uplift, for the same estimate.
ASSUMED_SERVICE_PLN = Decimal(230)

#: How far the component budget is cut on each retry, and how many retries.
BUDGET_RETRY_FACTOR = Decimal("0.90")
MAX_BUDGET_ATTEMPTS = 4


@dataclass(slots=True)
class BuildOption:
    """One priced, validated build."""

    tier: BuildTier
    parts: Parts
    quote: CommercialQuote
    report: CompatibilityReport
    performance_score: float
    notes: list[str]
    #: Whether the customer asked for the lighting to be shown off - the RGB
    #: priority or an RGB aesthetic. Capability is read from the parts.
    wants_lighting: bool = False

    @property
    def client_price_pln(self) -> Decimal:
        return self.quote.client_price_pln

    #: Kept for callers that predate the commercial pricing rewrite.
    @property
    def customer_total_pln(self) -> Decimal:
        return self.quote.client_price_pln

    @property
    def lighting(self) -> LightingPlan:
        """What these parts can light up and whether the customer asked.

        Computed from the parts, so the card, the fingerprint and the image
        prompt all answer the question the same way.
        """
        return plan_lighting(self.parts, requested=self.wants_lighting)

    @property
    def is_approximate(self) -> bool:
        """False only when every part has a verified market price."""
        return self.quote.is_approximate


class BuildService:
    def __init__(
        self,
        catalog: Catalog | None = None,
        market: MarketPriceService | None = None,
        settings: Settings | None = None,
        policy: PricingPolicy | None = None,
        config: PricingConfig | None = None,
    ) -> None:
        self._catalog = catalog or get_catalog()
        self._market = market or MarketPriceService()
        self._settings = settings or get_settings()
        self._policy = policy or self._settings.pricing_policy()
        self._config = config or get_pricing_config()

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    @property
    def policy(self) -> PricingPolicy:
        return self._policy

    @property
    def config(self) -> PricingConfig:
        return self._config

    def price_book(self) -> PriceBook:
        """Usable market price per component, for the generator to rank with.

        Verified prices win over estimates automatically because the market
        service resolves them in that order. Parts with no usable price are
        left out, so the generator never builds around a guess.
        """
        book: dict[str, Decimal] = {}
        for component in self._catalog:
            found = self._market.lookup(component.id)
            if found.usable and found.price_pln is not None:
                book[component.id] = found.price_pln
        return book

    def acquisition_budget(self, customer_budget_pln: int | Decimal) -> Decimal:
        """Estimated component budget inside a customer's total budget."""
        budget = Decimal(customer_budget_pln) - ASSUMED_SERVICE_PLN
        if budget <= 0:
            return Decimal(0)
        cost = budget / (Decimal(1) + ASSUMED_MARGIN_PERCENT / Decimal(100))
        return max(Decimal(0), cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def quote_for(self, parts: Parts) -> CommercialQuote:
        return price_quote(parts, self._policy, market=self._market, config=self._config)

    def build_options(self, requirements: BuildRequirements) -> list[BuildOption]:
        """Priced options for these requirements, cheapest first."""
        prices = self.price_book()
        customer_budget = Decimal(requirements.budget_pln)
        budget = self.acquisition_budget(requirements.budget_pln)

        # The component budget is an estimate, so a build can price out above
        # the customer's budget once real margins and the service tier are
        # applied. Shrink the component budget and try again rather than
        # showing nothing.
        for attempt in range(MAX_BUDGET_ATTEMPTS):
            if budget <= 0:
                break

            options = self._priced_options(requirements, prices, budget, customer_budget)
            if options:
                return options

            budget = (budget * BUDGET_RETRY_FACTOR).quantize(Decimal("0.01"))
            logger.debug(
                "Retrying with a %s PLN component budget (attempt %s)", budget, attempt + 2
            )

        logger.info("No build for budget %s PLN", requirements.budget_pln)
        return []

    def _priced_options(
        self,
        requirements: BuildRequirements,
        prices: PriceBook,
        acquisition_budget: Decimal,
        customer_budget: Decimal,
    ) -> list[BuildOption]:
        variants = generate_variants(
            requirements, self._catalog, prices, acquisition_budget_pln=acquisition_budget
        )
        options: list[BuildOption] = []

        for tier, build in variants.items():
            quote = self.quote_for(build.parts)
            if not quote.complete:
                logger.debug("Dropping %s: unpriced parts", tier.value)
                continue
            if quote.client_price_pln > customer_budget:
                logger.debug(
                    "Dropping %s: %s PLN over the %s PLN budget",
                    tier.value,
                    quote.client_price_pln,
                    customer_budget,
                )
                continue

            options.append(
                BuildOption(
                    tier=tier,
                    parts=build.parts,
                    quote=quote,
                    report=build.report,
                    performance_score=build.performance_score,
                    notes=build.notes,
                    wants_lighting=(
                        requirements.aesthetics.wants_rgb or requirements.wants(Priority.LOOKS)
                    ),
                )
            )

        options.sort(key=lambda option: option.client_price_pln)
        return options

    def recommended_option(self, requirements: BuildRequirements) -> BuildOption | None:
        """The option to show first: OPTIMAL when available, else the best fit."""
        options = self.build_options(requirements)
        if not options:
            return None
        for option in options:
            if option.tier is BuildTier.OPTIMAL:
                return option
        return options[-1]

    def minimum_customer_price_pln(self, requirements: BuildRequirements) -> Decimal | None:
        """Cheapest price we could honestly quote for this configuration."""
        cost = minimum_acquisition_cost(requirements, self._catalog, self.price_book())
        if cost is None:
            return None
        total = cost * (Decimal(1) + ASSUMED_MARGIN_PERCENT / Decimal(100)) + ASSUMED_SERVICE_PLN
        # Round up to the nearest 100 PLN - a precise-looking minimum invites
        # a customer to try exactly that number and fail on rounding.
        return (total / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP) * 100
