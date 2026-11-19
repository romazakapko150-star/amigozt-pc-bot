"""Retailer adapters.

Status: **none of these are connected.** Each class below is a real adapter
shell implementing :class:`PriceProvider`, with the integration route that the
retailer actually offers written down. They return no offers until credentials
and a lawful data source are in place, and they never fabricate a price.

Integration rules for whoever wires these up:

* Use an official API, an affiliate/partner product feed, or a written
  agreement. Do not scrape a site that forbids it - check ``robots.txt`` and
  the terms of service first, and honour rate limits.
* Fill in ``source_type`` honestly: ``STORE_API`` or ``PARTNER_FEED``.
* Set ``last_checked_at`` to the real fetch time so stale data is visible.
"""

from __future__ import annotations

import logging

from app.services.pricing.offers import Offer

logger = logging.getLogger(__name__)


class NotConnectedProvider:
    """Base for an adapter whose data source is not wired up yet.

    Returning nothing (rather than raising) means an unfinished integration
    degrades to "no offer from this store" instead of breaking a customer's
    build.
    """

    name = "not connected"
    #: How this retailer can lawfully be integrated.
    integration_route = "unknown"
    connected = False

    def get_offers(self, component_ids: list[str]) -> dict[str, list[Offer]]:
        logger.debug(
            "%s is not connected (%s); returning no offers", self.name, self.integration_route
        )
        return {}


class XKomProvider(NotConnectedProvider):
    name = "x-kom"
    integration_route = "affiliate programme / partner product feed - agreement required"


class MoreleProvider(NotConnectedProvider):
    name = "Morele"
    integration_route = "affiliate programme / partner product feed - agreement required"


class MediaExpertProvider(NotConnectedProvider):
    name = "Media Expert"
    integration_route = "affiliate network feed - agreement required"


class KomputronikProvider(NotConnectedProvider):
    name = "Komputronik"
    integration_route = "affiliate network feed - agreement required"


class RtvEuroAgdProvider(NotConnectedProvider):
    name = "RTV Euro AGD"
    integration_route = "affiliate network feed - agreement required"


class AmazonPlProvider(NotConnectedProvider):
    name = "Amazon.pl"
    integration_route = "Amazon Product Advertising API - associate account + API keys required"


class AliExpressProvider(NotConnectedProvider):
    name = "AliExpress"
    integration_route = "AliExpress Affiliate/Open Platform API - API keys required"


#: Every retailer adapter, in the order they would be queried.
RETAILER_PROVIDERS: tuple[type[NotConnectedProvider], ...] = (
    XKomProvider,
    MoreleProvider,
    MediaExpertProvider,
    KomputronikProvider,
    RtvEuroAgdProvider,
    AmazonPlProvider,
    AliExpressProvider,
)


def integration_status() -> list[dict[str, str | bool]]:
    """Machine-readable status for the admin panel and the README."""
    return [
        {
            "store": provider.name,
            "connected": provider.connected,
            "route": provider.integration_route,
        }
        for provider in RETAILER_PROVIDERS
    ]
