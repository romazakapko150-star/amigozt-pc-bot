"""Currency: one base for the business, several for the shop window.

Every price the system computes is in **PLN**. That is not a display
choice, it is the accounting base: suppliers invoice in złoty, the margin
policy is written in złoty, and every stored price column is złoty. This
module exists so that showing a price in another currency never turns into
*computing* in another currency.

Two rules follow from that, and both are enforced here rather than left to
callers:

* a conversion needs a real rate. There is no built-in table of made-up
  rates - :func:`convert` returns ``None`` when the rate for a pair is not
  configured, and the caller falls back to PLN. A wrong price shown
  confidently is worse than a price shown in złoty.
* the base never moves. ``Money`` carries its currency, and arithmetic
  between different currencies raises instead of silently coercing.

Rates, when they exist, are supplied by the caller (configuration, a feed,
a manual entry by the owner) - never guessed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENT = Decimal("0.01")


class Currency(StrEnum):
    PLN = "PLN"
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"


#: What the whole system computes in.
BASE_CURRENCY: Currency = Currency.PLN

#: How each currency is written for a customer. The symbol goes where that
#: currency's readers expect it.
_FORMATS: dict[Currency, str] = {
    Currency.PLN: "{amount} PLN",
    Currency.EUR: "€{amount}",
    Currency.USD: "${amount}",
    Currency.GBP: "£{amount}",
}


class CurrencyMismatch(ValueError):
    """Raised when two amounts in different currencies are combined."""


@dataclass(frozen=True, slots=True)
class Money:
    """An amount that knows what it is denominated in."""

    amount: Decimal
    currency: Currency = BASE_CURRENCY

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", Decimal(self.amount))

    def _check(self, other: Money) -> None:
        if self.currency is not other.currency:
            raise CurrencyMismatch(
                f"cannot combine {self.currency.value} with {other.currency.value}"
            )

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> Money:
        return Money(self.amount * Decimal(factor), self.currency)

    def quantized(self, exponent: Decimal = CENT) -> Money:
        return Money(self.amount.quantize(exponent, rounding=ROUND_HALF_UP), self.currency)

    @property
    def is_base(self) -> bool:
        return self.currency is BASE_CURRENCY


def zero(currency: Currency = BASE_CURRENCY) -> Money:
    return Money(Decimal(0), currency)


def pln(amount: Decimal | int | float) -> Money:
    """The constructor the rest of the code uses: everything starts as PLN."""
    return Money(Decimal(str(amount)), Currency.PLN)


def convert(
    money: Money, to: Currency, rates: dict[tuple[Currency, Currency], Decimal] | None = None
) -> Money | None:
    """``money`` expressed in ``to``, or ``None`` when no rate is known.

    ``rates`` maps ``(from, to)`` to a multiplier. Nothing is inverted or
    triangulated automatically: an inverse rate is a different number in the
    real world (spreads exist), so the caller supplies exactly the pairs it
    trusts.
    """
    if money.currency is to:
        return money
    rate = (rates or {}).get((money.currency, to))
    if rate is None:
        return None
    return Money(money.amount * Decimal(rate), to).quantized()


def format_money(money: Money) -> str:
    """``6 599 PLN`` / ``€1 499``: grouped thousands, whole units.

    Prices are shown whole on purpose - a build card quoting grosze reads
    like an invoice, not an offer.
    """
    whole = money.amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    grouped = f"{whole:,}".replace(",", " ")
    return _FORMATS[money.currency].format(amount=grouped)


def format_pln(amount: Decimal | int | float) -> str:
    """Shorthand for the base currency, matching ``domain.labels``."""
    return format_money(pln(amount))
