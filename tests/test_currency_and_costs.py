"""Currency architecture and the commercial cost breakdown.

Neither of these changes a single price the bot quotes today - that is the
point. They give the four business numbers explicit names and prepare a
second display currency without ever letting a display concern into the
arithmetic. The tests below are mostly about what must *not* happen: no
invented exchange rate, no currency mixing, and nothing internal leaking
onto a customer's card.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.labels import format_price_pln
from app.services.pricing.commercial import CostBreakdown
from app.services.pricing.currency import (
    BASE_CURRENCY,
    Currency,
    CurrencyMismatch,
    Money,
    convert,
    format_money,
    format_pln,
    pln,
    zero,
)

# --- the base currency ---------------------------------------------------------


def test_the_business_computes_in_zloty() -> None:
    assert BASE_CURRENCY is Currency.PLN
    assert pln(100).is_base
    assert zero().currency is Currency.PLN


def test_money_of_the_same_currency_adds_up() -> None:
    assert (pln(100) + pln(50)).amount == Decimal(150)
    assert (pln(100) - pln(50)).amount == Decimal(50)
    assert (pln(100) * 3).amount == Decimal(300)


def test_two_currencies_never_silently_merge() -> None:
    with pytest.raises(CurrencyMismatch):
        pln(100) + Money(Decimal(100), Currency.EUR)


# --- conversion ----------------------------------------------------------------


def test_no_rate_means_no_price_rather_than_a_guess() -> None:
    """The one rule: never show a converted price we cannot justify."""
    assert convert(pln(1000), Currency.EUR) is None
    assert convert(pln(1000), Currency.USD, rates={}) is None


def test_a_supplied_rate_is_used_exactly() -> None:
    rates = {(Currency.PLN, Currency.EUR): Decimal("0.23")}
    converted = convert(pln(1000), Currency.EUR, rates)
    assert converted is not None
    assert converted.currency is Currency.EUR
    assert converted.amount == Decimal("230.00")


def test_the_inverse_rate_is_not_invented() -> None:
    """Rates are not symmetric in the real world; we do not pretend they are."""
    rates = {(Currency.PLN, Currency.EUR): Decimal("0.23")}
    assert convert(Money(Decimal(230), Currency.EUR), Currency.PLN, rates) is None


def test_converting_to_the_same_currency_is_a_no_op() -> None:
    assert convert(pln(500), Currency.PLN) == pln(500)


# --- display -------------------------------------------------------------------


def test_the_new_formatter_matches_the_cards_the_bot_already_sends() -> None:
    for amount in (999, 4599, 6599, 19099):
        assert format_pln(amount) == format_price_pln(amount)


def test_each_currency_is_written_the_way_its_readers_expect() -> None:
    assert format_money(pln(6599)) == "6 599 PLN"
    assert format_money(Money(Decimal(1499), Currency.EUR)).startswith("€")
    assert format_money(Money(Decimal(1499), Currency.USD)).startswith("$")
    assert format_money(Money(Decimal(1499), Currency.GBP)).startswith("£")


def test_prices_are_shown_whole() -> None:
    assert format_money(pln(Decimal("6598.62"))) == "6 599 PLN"


# --- the commercial breakdown ---------------------------------------------------


def _breakdown() -> CostBreakdown:
    return CostBreakdown(
        supplier_cost_pln=Decimal(5200),
        internal_cost_pln=Decimal(200),
        margin_pln=Decimal(600),
        customer_price_pln=Decimal(6000),
    )


def test_the_four_numbers_add_up_to_the_price_the_customer_pays() -> None:
    """No hidden extra on top: the customer price *is* the whole sale."""
    breakdown = _breakdown()
    assert breakdown.balances
    assert (
        breakdown.supplier_cost_pln + breakdown.internal_cost_pln + breakdown.margin_pln
        == breakdown.customer_price_pln
    )


def test_the_margin_percent_is_of_the_selling_price() -> None:
    assert _breakdown().margin_percent == Decimal("10.0")


def test_a_breakdown_that_does_not_balance_says_so() -> None:
    broken = CostBreakdown(
        supplier_cost_pln=Decimal(5200),
        internal_cost_pln=Decimal(200),
        margin_pln=Decimal(600),
        customer_price_pln=Decimal(9999),
    )
    assert not broken.balances


def test_the_breakdown_can_speak_money() -> None:
    money = _breakdown().as_money()
    assert set(money) == {"supplier_cost", "internal_cost", "margin", "customer_price"}
    assert all(item.currency is Currency.PLN for item in money.values())
    assert format_money(money["customer_price"]) == "6 000 PLN"


def test_a_real_quote_produces_a_balanced_breakdown() -> None:
    """The named view must agree with the engine it reads from."""
    from app.config import Settings
    from app.domain.components import ComponentCategory as C
    from app.services.catalog import get_catalog
    from app.services.pricing.commercial import quote
    from tests.fake_telegram import FAKE_TOKEN

    catalog = get_catalog()
    parts = {
        C.CPU: catalog.require("amd-ryzen-7-9700x"),
        C.COOLER: catalog.require("thermalright-assassin-x-120-refined-se"),
        C.MOTHERBOARD: catalog.require("msi-b650-gaming-plus-wifi"),
        C.RAM: catalog.require("kingston-fury-beast-32-ddr5-6000"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        C.PSU: catalog.require("bequiet-pure-power-12m-850"),
        C.CASE: catalog.require("fractal-pop-air-black"),
    }
    settings = Settings(telegram_bot_token=FAKE_TOKEN)  # type: ignore[call-arg]
    result = quote(parts, settings.pricing_policy())
    breakdown = result.cost_breakdown()

    assert breakdown.customer_price_pln == result.client_price_pln
    assert breakdown.supplier_cost_pln == result.purchase_cost_pln
    assert breakdown.margin_pln == result.net_profit_pln
    assert breakdown.balances, "the named view must reconcile with the engine"
