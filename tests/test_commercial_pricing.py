"""Commercial pricing v3: margin ranges, the profit optimiser, assembly tiers,
operating costs, profit tiers, rounding, provenance - and the twelve scenarios
from the owner's brief, each printed as the table the owner asked for.

Market prices in the fixtures are deliberately *examples*, recorded through
the same verified-price file the production bot reads, so the tests exercise
the real path.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.bot.flows.configurator import build_requirements
from app.domain.components import ComponentCategory
from app.services.catalog import get_catalog
from app.services.pricing import (
    CommercialQuote,
    Competitiveness,
    ComplexityLevel,
    MarketPriceService,
    PriceStatus,
    PricingPolicy,
    calculate_customer_price,
    check_competitiveness,
    commercial_round,
    get_pricing_config,
    load_pricing_config,
    price_product,
    quote,
    round_to_nine,
    validate_build,
)
from app.services.recommendation import BuildService

C = ComponentCategory
TODAY = date(2026, 8, 22)


@pytest.fixture(scope="module")
def catalog():  # type: ignore[no-untyped-def]
    return get_catalog()


@pytest.fixture(scope="module")
def config():  # type: ignore[no-untyped-def]
    return get_pricing_config()


@pytest.fixture
def policy() -> PricingPolicy:
    return PricingPolicy()


def _market_file(tmp_path: Path, prices: dict[str, dict]) -> Path:
    path = tmp_path / "market.json"
    path.write_text(
        json.dumps({"_meta": {"stale_after_days": 14}, "prices": prices}), encoding="utf-8"
    )
    return path


def _verified(price: float, days_old: int = 0, source: str = "x-kom") -> dict:
    return {
        "price": price,
        "source": source,
        "url": f"https://{source}.pl/p/example",
        "checked_at": (TODAY - timedelta(days=days_old)).isoformat(),
    }


@pytest.fixture
def market(tmp_path: Path) -> MarketPriceService:
    return MarketPriceService(
        market_file=_market_file(
            tmp_path,
            {
                "huzaro-hero-desk": _verified(319),
                "amd-rx-9070-xt": _verified(3000, source="morele"),
                "lianli-lancool-216-black": _verified(459),
                "steelseries-qck-heavy-l": _verified(119, days_old=40),  # historical
            },
        ),
        today=TODAY,
    )


@pytest.fixture(scope="module")
def pc_parts(catalog):  # type: ignore[no-untyped-def]
    """The owner's worked example: purchase cost 5 680 PLN."""
    return {
        C.CPU: catalog.require("amd-ryzen-5-7600"),
        C.GPU: catalog.require("amd-rx-7800-xt"),
        C.MOTHERBOARD: catalog.require("msi-b650-gaming-plus-wifi"),
        C.RAM: catalog.require("kingston-fury-beast-32-ddr5-6000"),
        C.SSD: catalog.require("samsung-990-evo-1tb"),
        C.PSU: catalog.require("corsair-rm750e"),
        C.CASE: catalog.require("fractal-pop-air-black"),
        C.COOLER: catalog.require("thermalright-peerless-assassin-120-se"),
    }


def _table(title: str, q: CommercialQuote) -> None:
    """The per-scenario table the brief asks for. Shown with ``pytest -s``."""
    print(
        f"\n[{title}] purchase {q.purchase_cost_pln} | customer {q.client_price_pln} | "
        f"assembly {q.assembly_tier_name} {q.assembly_fee_pln} | gross {q.gross_profit_pln} | "
        f"net {q.net_profit_pln} | margin {q.margin_percent}% | {q.profit_tier.label} | "
        f"margin position {q.margin_position:.0%}"
    )


def _requirements(budget: int, **overrides: object):  # type: ignore[no-untyped-def]
    answers = {
        "budget_pln": budget,
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


# --- the formula ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("366.85", 369), ("527.40", 529), (319, 319), (320, 329), (3150, 3159)],
)
def test_item_rounding_ends_in_nine(raw: object, expected: int) -> None:
    assert round_to_nine(Decimal(str(raw))) == Decimal(expected)


@pytest.mark.parametrize(
    ("raw", "expected"), [(6387, 6399), (6421, 6449), (6478, 6499), (6399, 6399), (6450, 6499)]
)
def test_total_rounding_ends_in_49_or_99(raw: int, expected: int) -> None:
    assert commercial_round(Decimal(raw)) == Decimal(expected)


def test_rounding_only_moves_up() -> None:
    for value in range(15, 12000, 37):
        assert round_to_nine(Decimal(value)) >= value
        assert commercial_round(Decimal(value)) >= value


def test_owners_desk_example_at_low_margin(config) -> None:  # type: ignore[no-untyped-def]
    """Huzaro Hero 4.0 at 319 PLN: desk 10-20 %, band minimum 50 → 369 PLN."""
    price, rule = calculate_customer_price(Decimal(319), C.DESK, config=config)
    assert rule.margin_percent == Decimal(10)
    assert rule.min_profit_pln == Decimal(50)
    assert price == Decimal(369)


def test_margin_position_moves_through_the_range(config) -> None:  # type: ignore[no-untyped-def]
    low, _ = calculate_customer_price(Decimal(3000), C.GPU, config=config)
    high, rule = calculate_customer_price(Decimal(3000), C.GPU, position=Decimal(1), config=config)
    assert rule.margin_percent == Decimal(9)
    assert high > low


def test_expensive_gpu_never_carries_a_huge_markup(config) -> None:  # type: ignore[no-untyped-def]
    """Even at the top of its range a 2 200 PLN GPU stays far below 2 700."""
    price, _ = calculate_customer_price(Decimal(2200), C.GPU, position=Decimal(1), config=config)
    assert price <= Decimal(2450)


def test_cheap_accessory_hits_the_band_minimum(config) -> None:  # type: ignore[no-untyped-def]
    price, rule = calculate_customer_price(Decimal(60), C.MOUSEPAD, config=config)
    assert rule.min_profit_pln == Decimal(30)
    assert price - Decimal(60) >= Decimal(30)


def test_ranges_are_configurable_from_json(tmp_path: Path) -> None:
    raw = json.loads(Path("app/data/pricing/margins.json").read_text(encoding="utf-8"))
    raw["category_margin_range"]["gpu"] = [20, 30]
    raw["assembly"]["tiers"]["standard"]["fee_pln"] = 249
    raw["profit"]["target_order_profit_pln"] = 1200
    custom = tmp_path / "margins.json"
    custom.write_text(json.dumps(raw), encoding="utf-8")

    cfg = load_pricing_config(custom)
    assert cfg.margin_range_for(C.GPU).low == Decimal(20)
    assert cfg.assembly_tier("standard").fee_pln == Decimal(249)
    assert cfg.profit.target_order_profit_pln == Decimal(1200)


def test_every_catalogue_category_has_a_range(catalog, config) -> None:  # type: ignore[no-untyped-def]
    for component in catalog:
        rng = config.margin_range_for(component.category)
        assert rng.low > 0 and rng.high >= rng.low


# --- market prices and provenance -------------------------------------------------


def test_verified_price_is_used_as_is(market: MarketPriceService) -> None:
    found = market.lookup("huzaro-hero-desk")
    assert found.status is PriceStatus.VERIFIED
    assert found.price_pln == Decimal(319)
    assert found.source == "x-kom" and found.checked_at == TODAY


def test_estimate_is_labelled(market: MarketPriceService) -> None:
    assert market.lookup("amd-ryzen-7-7800x3d").status is PriceStatus.ESTIMATED


def test_unknown_is_unknown(market: MarketPriceService) -> None:
    found = market.lookup("does-not-exist")
    assert found.status is PriceStatus.UNKNOWN and not found.usable


def test_stale_verified_price_is_historical(market: MarketPriceService, catalog) -> None:  # type: ignore[no-untyped-def]
    found = market.lookup("steelseries-qck-heavy-l")
    assert found.status is PriceStatus.HISTORICAL
    assert price_product(catalog.require("steelseries-qck-heavy-l"), found) is None


def test_verified_beats_the_old_estimate(market: MarketPriceService) -> None:
    assert market.lookup("huzaro-hero-desk").price_pln == Decimal(319)
    assert market.historical_estimate("huzaro-hero-desk") == Decimal(550)


# --- assembly, validation, competitiveness ------------------------------------------


def test_assembly_tiers_are_paid_and_configurable(config) -> None:  # type: ignore[no-untyped-def]
    basic = config.assembly_tier("basic")
    standard = config.assembly_tier("standard")
    premium = config.assembly_tier("premium")
    assert (basic.fee_pln, standard.fee_pln, premium.fee_pln) == (149, 199, 299)
    assert "stress_test" in standard.includes
    assert "photos_of_finished_pc" in premium.includes
    assert config.assembly_key_for(ComplexityLevel.EASY) == "basic"
    assert config.assembly_key_for(ComplexityLevel.COMPLEX) == "premium"


def test_profit_tiers(config) -> None:  # type: ignore[no-untyped-def]
    assert config.profit_tier_for(Decimal(250)).name == "LOW"
    assert config.profit_tier_for(Decimal(600)).name == "ACCEPTABLE"
    assert config.profit_tier_for(Decimal(811)).name == "TARGET"
    assert config.profit_tier_for(Decimal(950)).name == "GOOD"
    assert config.profit_tier_for(Decimal(1200)).name == "EXCELLENT"


def test_validator_labels_without_changing_prices(config) -> None:  # type: ignore[no-untyped-def]
    tier = config.assembly_tier("standard")
    check = validate_build(Decimal(5680), Decimal(612), tier, config=config)
    assert check.total_profit_pln == Decimal(811)
    assert check.tier.name == "TARGET"
    assert not check.warnings
    weak = validate_build(Decimal(6000), Decimal(50), tier, config=config)
    assert weak.warnings and weak.tier.name == "LOW"


def test_competitiveness_warns_above_market() -> None:
    report = check_competitiveness(Decimal(7200), Decimal(6300), Decimal(6500))
    assert report.status is Competitiveness.ABOVE_MARKET
    assert report.difference_percent == Decimal("10.8")
    good = check_competitiveness(Decimal(6599), Decimal(6300), Decimal(6500))
    assert good.status is Competitiveness.COMPETITIVE


# --- the optimiser ----------------------------------------------------------------


def test_optimiser_reaches_target_by_spreading_margin(pc_parts, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    """5 680 PLN of parts at low margins earns ~600; the optimiser lifts every
    category together until the order clears the 850 PLN target."""
    q = quote(pc_parts, policy)
    _table("5 680 PLN build", q)

    assert q.purchase_cost_pln == Decimal(5680)
    assert q.gross_profit_pln >= q.config.profit.target_order_profit_pln
    assert q.margin_position > 0
    # Every priced category moved by the same fraction of its range.
    positions = {item.rule.position for item in q.items.values()}
    assert len(positions) == 1
    # And the GPU is still modestly priced.
    gpu = q.items[C.GPU]
    assert gpu.rule.margin_percent <= Decimal(9)
    assert gpu.customer_price_pln <= Decimal(2450)


def test_optimiser_does_not_over_reach(pc_parts, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    """Once target is met it stops - the customer is not charged for 'excellent'."""
    q = quote(pc_parts, policy)
    target = q.config.profit.target_order_profit_pln
    assert target <= q.gross_profit_pln < target + Decimal(250)


def test_market_reference_caps_the_optimiser(pc_parts, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    free = quote(pc_parts, policy)
    capped = quote(
        pc_parts,
        policy,
        market_reference_low_pln=Decimal(6000),
        market_reference_high_pln=Decimal(6100),
    )
    assert capped.client_price_pln <= free.client_price_pln
    assert capped.margin_position <= free.margin_position


def test_price_identity(pc_parts, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    q = quote(pc_parts, policy)
    assert (
        q.raw_sale_price_pln == q.components_price_pln + q.assembly_fee_pln + q.other_services_pln
    )
    assert q.client_price_pln == commercial_round(q.raw_sale_price_pln)
    assert q.gross_profit_pln == (q.product_profit_pln + q.assembly_fee_pln + q.rounding_uplift_pln)
    assert q.net_profit_pln == q.gross_profit_pln - q.operating_costs_pln
    assert q.client_price_pln % 50 == 49


def test_snapshot_holds_all_ten_numbers(pc_parts, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    snapshot = quote(pc_parts, policy).as_snapshot()
    json.dumps(snapshot)
    for key in (
        "market_cost_pln",
        "purchase_cost_pln",
        "sale_price_pln",
        "product_profit_pln",
        "assembly_fee_pln",
        "other_services_pln",
        "gross_profit_pln",
        "operating_costs_pln",
        "net_profit_pln",
        "margin_percent",
        "profit_tier",
        "items",
    ):
        assert key in snapshot, key


# --- the twelve scenarios ---------------------------------------------------------


@pytest.fixture(scope="module")
def service() -> BuildService:
    return BuildService()


@pytest.mark.parametrize("budget", [3000, 5000, 7000, 10000])
def test_scenario_pc_by_budget(service: BuildService, budget: int) -> None:
    options = service.build_options(_requirements(budget))
    if budget == 3000:
        # Below the catalogue's floor: the bot says so rather than forcing a loss.
        assert options == []
        assert service.minimum_customer_price_pln(_requirements(3000)) is not None
        return

    assert options, f"no build for {budget} PLN"
    for option in options:
        q = option.quote
        _table(f"PC {budget} PLN · {option.tier.value}", q)
        assert q.client_price_pln <= budget
        assert not q.profit_check.is_loss
        assert q.assembly_fee_pln >= Decimal(149)
        assert q.gross_profit_pln >= q.config.profit.minimum_order_profit_pln


def test_scenario_cheap_accessory(catalog, market: MarketPriceService) -> None:  # type: ignore[no-untyped-def]
    mouse = catalog.require("steelseries-rival-3")
    priced = price_product(mouse, market.lookup(mouse.id))
    assert priced is not None
    print(
        f"\n[cheap accessory] market {priced.market_price_pln} -> "
        f"{priced.customer_price_pln}, profit {priced.profit_pln}"
    )
    assert priced.profit_pln >= Decimal(30)


def test_scenario_expensive_gpu(catalog, market: MarketPriceService) -> None:  # type: ignore[no-untyped-def]
    gpu = catalog.require("amd-rx-9070-xt")
    priced = price_product(gpu, market.lookup(gpu.id))
    assert priced is not None and priced.market.is_verified
    print(
        f"\n[expensive GPU] market 3000 -> {priced.customer_price_pln}, profit {priced.profit_pln}"
    )
    assert priced.customer_price_pln == Decimal(3159)


def test_scenario_order_with_monitor(pc_parts, catalog, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    bundle = dict(pc_parts)
    bundle[C.MONITOR] = catalog.require("gigabyte-m27q")
    q = quote(bundle, policy)
    _table("PC + monitor", q)
    assert C.MONITOR in q.items
    pc_only = quote(pc_parts, policy)
    # The monitor brings its own margin, so the target is reached with *less*
    # mark-up on the PC parts - the customer is not charged twice.
    assert q.gross_profit_pln >= q.config.profit.target_order_profit_pln
    assert q.margin_position <= pc_only.margin_position
    assert q.client_price_pln > pc_only.client_price_pln


def test_scenario_order_with_accessories(
    pc_parts, catalog, policy: PricingPolicy, market: MarketPriceService
) -> None:  # type: ignore[no-untyped-def]
    bundle = dict(pc_parts)
    bundle[C.DESK] = catalog.require("huzaro-hero-desk")
    bundle[C.MOUSE] = catalog.require("logitech-g305")
    bundle[C.HEADSET] = catalog.require("hyperx-cloud-ii")
    q = quote(bundle, policy, market=market)
    _table("PC + accessories", q)
    assert q.items[C.DESK].market.is_verified
    assert q.gross_profit_pln >= q.config.profit.target_order_profit_pln


def test_scenario_order_without_accessories(pc_parts, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    q = quote(pc_parts, policy)
    _table("PC only", q)
    assert set(q.items) == set(pc_parts)
    assert q.meets_target_profit


def test_scenario_low_profit_order(policy: PricingPolicy, config, catalog) -> None:  # type: ignore[no-untyped-def]
    """A cheap office box cannot reach 700 PLN even at maximum margins - the
    engine raises what it honestly can and warns, instead of inflating."""
    parts = {
        C.CPU: catalog.require("amd-ryzen-5-7600"),
        C.MOTHERBOARD: catalog.require("gigabyte-b650m-ds3h"),
        C.RAM: catalog.require("kingston-fury-beast-16-ddr5-6000"),
        C.SSD: catalog.require("kingston-nv3-500"),
        C.PSU: catalog.require("bequiet-system-power-10-550"),
        C.CASE: catalog.require("montech-air-100-argb"),
    }
    q = quote(parts, policy)
    _table("low-profit office box", q)
    assert q.margin_position == Decimal(1)
    assert q.gross_profit_pln < config.profit.minimum_order_profit_pln
    assert q.profit_tier.name in {"LOW", "ACCEPTABLE"}
    assert any("below the" in w for w in q.warnings)


def test_scenario_good_profit_order(catalog, policy: PricingPolicy) -> None:  # type: ignore[no-untyped-def]
    parts = {
        C.CPU: catalog.require("amd-ryzen-7-9800x3d"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.MOTHERBOARD: catalog.require("asus-rog-strix-x670e-a"),
        C.RAM: catalog.require("corsair-vengeance-rgb-32-ddr5-6000"),
        C.SSD: catalog.require("samsung-990-pro-2tb"),
        C.PSU: catalog.require("seasonic-vertex-gx-1000"),
        C.CASE: catalog.require("lianli-o11-dynamic-evo-white"),
        C.COOLER: catalog.require("arctic-liquid-freezer-iii-360-white"),
    }
    q = quote(parts, policy)
    _table("high-end build", q)
    assert q.gross_profit_pln >= q.config.profit.good_order_profit_pln
    assert q.profit_tier.name in {"GOOD", "EXCELLENT"}


def test_scenario_product_without_a_current_price(
    pc_parts, policy: PricingPolicy, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    empty = tmp_path / "estimates.json"
    empty.write_text(json.dumps({"prices": {}}), encoding="utf-8")
    bare = MarketPriceService(
        market_file=_market_file(tmp_path, {}), estimate_file=empty, today=TODAY
    )
    q = quote(pc_parts, policy, market=bare)
    assert not q.complete
    assert all(m.status is PriceStatus.UNKNOWN for m in q.unpriced.values())
    assert any("no usable market price" in w for w in q.warnings)
