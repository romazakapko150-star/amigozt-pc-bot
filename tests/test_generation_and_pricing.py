"""Build generation, pricing, margin and the customer/admin data boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from app.bot.flows.configurator import build_requirements
from app.config import Settings
from app.domain.components import ComponentCategory, CpuSpec, GpuSpec
from app.domain.enums import BuildTier, CpuBrand, GpuBrand
from app.services.catalog import get_catalog
from app.services.compatibility import validate
from app.services.pricing import (
    Availability,
    EstimatePriceProvider,
    Offer,
    OfferSource,
    PriceService,
    Strategy,
    integration_status,
    select_offer,
)
from app.services.recommendation import BuildService, generate_variants, minimum_acquisition_cost
from tests.fake_telegram import FAKE_TOKEN


def _requirements(**overrides: object):  # type: ignore[no-untyped-def]
    answers = {
        "budget_pln": 6000,
        "purpose": "gaming",
        "games": ["cs2"],
        "resolution": "1440p",
        "target_fps": "144",
        "priority": "price_performance",
        "aesthetics": "black",
        "wifi": False,
        "bluetooth": False,
        "storage_gb": 1000,
        "ram_gb": 32,
        "cpu_brand": "any",
        "gpu_brand": "any",
    }
    answers.update(overrides)
    return build_requirements(answers)


@pytest.fixture(scope="module")
def service() -> BuildService:
    settings = Settings(  # type: ignore[call-arg]
        telegram_bot_token=FAKE_TOKEN,
        target_hourly_earnings_pln=Decimal(150),
        minimum_profit_per_order_pln=Decimal(500),
        minimum_profit_per_hour_pln=Decimal(100),
    )
    return BuildService(settings=settings)


@pytest.fixture(scope="module")
def prices() -> dict[str, Decimal]:
    catalog = get_catalog()
    provider = EstimatePriceProvider()
    offers = provider.get_offers([component.id for component in catalog])
    return {cid: found[0].price_pln for cid, found in offers.items() if found}


# --- generation ---------------------------------------------------------------


def test_every_generated_build_is_compatible(service: BuildService) -> None:
    for option in service.build_options(_requirements()):
        report = validate(option.parts)
        assert report.ok, [issue.detail for issue in report.errors]


def test_generated_builds_contain_every_required_part(service: BuildService) -> None:
    options = service.build_options(_requirements())
    assert options
    for option in options:
        for category in (
            ComponentCategory.CPU,
            ComponentCategory.MOTHERBOARD,
            ComponentCategory.RAM,
            ComponentCategory.SSD,
            ComponentCategory.PSU,
            ComponentCategory.CASE,
        ):
            assert category in option.parts


def test_build_stays_within_the_customer_budget(service: BuildService) -> None:
    for budget in (5000, 6000, 8000, 12000):
        for option in service.build_options(_requirements(budget_pln=budget)):
            assert option.customer_total_pln <= budget, f"{option.tier} exceeded {budget}"


def test_tiers_never_go_backwards(service: BuildService) -> None:
    """A pricier tier must not be slower - customers compare them side by side."""
    options = service.build_options(_requirements(budget_pln=12000))
    assert len(options) >= 2
    for cheaper, dearer in pairwise(options):
        assert dearer.customer_total_pln >= cheaper.customer_total_pln
        assert dearer.performance_score >= cheaper.performance_score


def test_tiers_are_distinct_when_the_budget_allows(service: BuildService) -> None:
    options = service.build_options(_requirements(budget_pln=12000))
    signatures = {tuple(sorted(c.id for c in option.parts.values())) for option in options}
    assert len(signatures) == len(options)


@pytest.mark.parametrize(("preference", "expected_brand"), [("amd", "AMD"), ("intel", "Intel")])
def test_cpu_brand_preference_is_honoured(
    service: BuildService, preference: str, expected_brand: str
) -> None:
    options = service.build_options(_requirements(cpu_brand=preference))
    assert options
    for option in options:
        assert option.parts[ComponentCategory.CPU].brand == expected_brand


@pytest.mark.parametrize(
    ("preference", "expected_brand"),
    [("nvidia", "NVIDIA"), ("amd", "AMD"), ("intel", "Intel")],
)
def test_gpu_brand_preference_is_honoured(
    service: BuildService, preference: str, expected_brand: str
) -> None:
    options = service.build_options(_requirements(gpu_brand=preference))
    assert options
    for option in options:
        assert option.parts[ComponentCategory.GPU].brand == expected_brand


def test_both_brand_preferences_together(service: BuildService) -> None:
    options = service.build_options(
        _requirements(budget_pln=9000, cpu_brand="intel", gpu_brand="nvidia")
    )
    assert options
    for option in options:
        assert option.parts[ComponentCategory.CPU].brand == "Intel"
        assert option.parts[ComponentCategory.GPU].brand == "NVIDIA"


def test_wifi_requirement_selects_a_wifi_motherboard(service: BuildService) -> None:
    for option in service.build_options(_requirements(wifi=True, bluetooth=True)):
        board = option.parts[ComponentCategory.MOTHERBOARD]
        assert getattr(board.spec, "wifi", False)
        assert getattr(board.spec, "bluetooth", False)


def test_requested_memory_and_storage_are_respected(service: BuildService) -> None:
    for option in service.build_options(
        _requirements(ram_gb=64, storage_gb=2000, budget_pln=12000)
    ):
        assert option.parts[ComponentCategory.RAM].spec.total_capacity_gb >= 64
        assert option.parts[ComponentCategory.SSD].spec.capacity_gb >= 2000


def test_higher_budget_never_buys_less_performance(service: BuildService) -> None:
    cheap = service.recommended_option(_requirements(budget_pln=5000))
    rich = service.recommended_option(_requirements(budget_pln=12000))
    assert cheap is not None and rich is not None
    assert rich.performance_score > cheap.performance_score


def test_impossible_budget_returns_no_options_and_a_minimum(service: BuildService) -> None:
    requirements = _requirements(budget_pln=2500)
    assert service.build_options(requirements) == []

    minimum = service.minimum_customer_price_pln(requirements)
    assert minimum is not None
    assert minimum > 2500


def test_high_fps_targets_do_not_break_generation(service: BuildService) -> None:
    for fps in ("300+", "500+", "700+"):
        options = service.build_options(_requirements(target_fps=fps, budget_pln=9000))
        assert options, f"no build for target {fps}"


def test_office_build_can_use_integrated_graphics(service: BuildService) -> None:
    """A work PC must not be forced to buy a discrete GPU."""
    options = generate_variants(
        _requirements(purpose="work", games=[], budget_pln=4000, ram_gb=16),
        get_catalog(),
        {
            cid: offer[0].price_pln
            for cid, offer in EstimatePriceProvider()
            .get_offers([c.id for c in get_catalog()])
            .items()
        },
        acquisition_budget_pln=Decimal(3000),
    )
    assert options
    igpu_builds = [b for b in options.values() if ComponentCategory.GPU not in b.parts]
    for build in igpu_builds:
        cpu_spec = build.parts[ComponentCategory.CPU].spec
        assert isinstance(cpu_spec, CpuSpec)
        assert cpu_spec.integrated_graphics


def test_minimum_cost_ignores_the_budget(prices: dict[str, Decimal]) -> None:
    cost = minimum_acquisition_cost(_requirements(budget_pln=2500), get_catalog(), prices)
    assert cost is not None and cost > 0


def test_psu_always_covers_the_gpu_recommendation(service: BuildService) -> None:
    for option in service.build_options(_requirements(budget_pln=12000)):
        gpu = option.parts.get(ComponentCategory.GPU)
        psu = option.parts[ComponentCategory.PSU]
        if gpu is None:
            continue
        assert isinstance(gpu.spec, GpuSpec)
        assert psu.spec.wattage >= gpu.spec.recommended_psu_w * 0.9


# --- pricing ------------------------------------------------------------------


def _offer(price: int, **kwargs: object) -> Offer:
    defaults: dict = {
        "component_id": "x",
        "store": "s",
        "price_pln": Decimal(price),
        "availability": Availability.IN_STOCK,
        "source_type": OfferSource.STORE_API,
        "last_checked_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return Offer(**defaults)  # type: ignore[arg-type]


def test_best_price_picks_the_cheapest_total() -> None:
    offers = [
        _offer(3000, store="A"),
        _offer(2900, store="B", shipping_pln=Decimal(200)),
        _offer(2950, store="C"),
    ]
    chosen = select_offer(offers, Strategy.BEST_PRICE)
    assert chosen is not None and chosen.store == "C"


def test_best_value_avoids_an_out_of_stock_bargain() -> None:
    offers = [
        _offer(2500, store="Cheap", availability=Availability.OUT_OF_STOCK),
        _offer(2700, store="Stocked"),
    ]
    chosen = select_offer(offers, Strategy.BEST_VALUE)
    assert chosen is not None and chosen.store == "Stocked"


def test_fastest_delivery_strategy() -> None:
    offers = [
        _offer(2500, store="Slow", delivery_days=7),
        _offer(2700, store="Fast", delivery_days=1),
    ]
    chosen = select_offer(offers, Strategy.FASTEST_DELIVERY)
    assert chosen is not None and chosen.store == "Fast"


def test_most_trusted_strategy() -> None:
    offers = [
        _offer(2500, store="Unknown", store_trust=20),
        _offer(2700, store="Known", store_trust=90),
    ]
    chosen = select_offer(offers, Strategy.MOST_TRUSTED)
    assert chosen is not None and chosen.store == "Known"


def test_no_offers_means_no_choice() -> None:
    assert select_offer([]) is None


def test_offer_age_is_reported() -> None:
    stale = _offer(100, last_checked_at=datetime.now(UTC) - timedelta(days=5))
    assert stale.age_days() == 5


def test_estimate_provider_marks_its_prices_as_estimates() -> None:
    provider = EstimatePriceProvider()
    offers = provider.get_offers(["amd-ryzen-7-7800x3d"])
    offer = offers["amd-ryzen-7-7800x3d"][0]
    assert offer.source_type is OfferSource.ESTIMATE
    assert offer.is_estimate


def test_unknown_component_simply_has_no_offer() -> None:
    assert EstimatePriceProvider().get_offers(["does-not-exist"]) == {}


def test_no_retailer_is_claimed_to_be_connected() -> None:
    """Guards against an adapter shell being presented as a live integration."""
    for entry in integration_status():
        assert entry["connected"] is False
        assert entry["route"]


def test_a_failing_provider_does_not_break_pricing() -> None:
    class Broken:
        name = "broken"

        def get_offers(self, component_ids: list[str]) -> dict[str, list[Offer]]:
            raise RuntimeError("upstream down")

    service = PriceService(providers=[Broken(), EstimatePriceProvider()])  # type: ignore[list-item]
    catalog = get_catalog()
    parts = {ComponentCategory.CPU: catalog.require("amd-ryzen-7-7800x3d")}
    breakdown = service.price_parts(parts)
    assert breakdown.complete


# --- margin and the data boundary --------------------------------------------


def test_price_is_parts_plus_assembly_rounded_up(service: BuildService) -> None:
    option = service.recommended_option(_requirements())
    assert option is not None

    quote = option.quote
    assert quote.raw_sale_price_pln == quote.components_price_pln + quote.service_fee_pln
    # Rounding only ever moves the price up, and the total ends in 49 or 99.
    assert quote.client_price_pln >= quote.raw_sale_price_pln
    assert quote.client_price_pln % 50 == 49
    # Every part carries its own margin; the total profit is parts + service + rounding.
    assert quote.gross_profit_pln == (
        quote.product_profit_pln + quote.service_fee_pln + quote.rounding_uplift_pln
    )


def test_profit_clears_the_build_minimum(service: BuildService) -> None:
    option = service.recommended_option(_requirements())
    assert option is not None
    quote = option.quote
    assert quote.gross_profit_pln >= quote.config.minimum_build_profit_pln
    assert not quote.profit_check.is_loss


def test_acquisition_budget_leaves_room_for_labour_and_margin(service: BuildService) -> None:
    budget = service.acquisition_budget(6000)
    assert budget < Decimal(6000)
    # Margin plus the service fee must fit inside the gap.
    assert Decimal(6000) - budget > Decimal(500)


def test_build_card_never_shows_acquisition_cost_or_margin(service: BuildService) -> None:
    """The customer-facing renderer must not leak admin numbers."""
    from app.bot.views.build import render_build_card

    option = service.recommended_option(_requirements())
    assert option is not None

    quote = option.quote
    # Admin-only numbers. Short values (a lone "0") would match anything, so
    # only meaningful amounts are checked.
    secrets = [
        value
        for value in (
            str(int(quote.market_cost_pln)),
            str(int(quote.gross_profit_pln)),
            str(int(quote.product_profit_pln)),
            str(int(quote.labor_value_pln)),
            str(int(quote.profit_per_hour_pln)),
            str(quote.estimated_total_hours),
        )
        if len(value) >= 3
    ]

    for lang in ("ru", "pl", "en", "uk"):
        card = render_build_card(option, lang).replace(" ", "")
        for secret in secrets:
            assert secret not in card, f"{secret} leaked into the {lang} card"
        assert "margin" not in card.lower()


def test_estimated_prices_are_flagged_as_approximate(service: BuildService) -> None:
    option = service.recommended_option(_requirements())
    assert option is not None
    assert option.is_approximate is True


def test_tier_enum_values_all_render(service: BuildService) -> None:
    from app.i18n import SUPPORTED_LANGUAGES, t

    for tier in BuildTier:
        for lang in SUPPORTED_LANGUAGES:
            label = t(lang, f"build.tier.{tier.value}")
            assert not label.startswith("build.tier")


def test_brand_enums_cover_the_catalogue() -> None:
    catalog = get_catalog()
    cpu_brands = {c.brand for c in catalog.by_category(ComponentCategory.CPU)}
    gpu_brands = {c.brand for c in catalog.by_category(ComponentCategory.GPU)}
    assert cpu_brands <= {"AMD", "Intel"}
    assert gpu_brands <= {"NVIDIA", "AMD", "Intel"}
    assert {CpuBrand.AMD, CpuBrand.INTEL} <= set(CpuBrand)
    assert {GpuBrand.NVIDIA, GpuBrand.AMD, GpuBrand.INTEL} <= set(GpuBrand)
