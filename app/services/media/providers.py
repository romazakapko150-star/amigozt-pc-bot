"""Product image sources.

Status: **none connected.** Real product photography needs either a licensed
image source or a retailer/manufacturer feed that permits reuse. Until one is
in place the bot shows its own generated build card (see
:mod:`app.services.media.build_image`) and never presents it as a photograph.

Integration rules:

* Only use images the shop is licensed to use: manufacturer press kits,
  an authorised retailer feed, or a paid stock/licensed source.
* Store the URL and its provenance, not a local copy, unless the licence
  requires otherwise.
* Never hotlink an image found through a search engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger(__name__)


class ImageSourceType(StrEnum):
    OFFICIAL_MANUFACTURER = "official_manufacturer"
    OFFICIAL_STORE = "official_store"
    RETAILER = "retailer"
    MARKETPLACE = "marketplace"
    #: Drawn by us. Must always be labelled as a visualisation.
    GENERATED = "generated"
    USER_UPLOADED = "user_uploaded"


@dataclass(frozen=True, slots=True)
class ProductImage:
    component_id: str
    url: str
    source: str
    source_type: ImageSourceType
    is_primary: bool = False

    @property
    def is_real_photo(self) -> bool:
        return self.source_type is not ImageSourceType.GENERATED


class ImageProvider(Protocol):
    """Contract for a product image source."""

    name: str
    connected: bool

    def get_images(self, component_ids: list[str]) -> dict[str, list[ProductImage]]:
        """Images per component id. Missing ids simply have no entry."""
        ...


class NotConnectedImageProvider:
    """Adapter shell for a source that is not wired up yet."""

    name = "not connected"
    licence_route = "unknown"
    connected = False

    def get_images(self, component_ids: list[str]) -> dict[str, list[ProductImage]]:
        return {}


class ManufacturerImageProvider(NotConnectedImageProvider):
    name = "manufacturer press kits"
    licence_route = "per-brand press/media kit terms - usually free for resellers, needs checking"


class RetailerFeedImageProvider(NotConnectedImageProvider):
    name = "retailer product feed"
    licence_route = "affiliate/partner feed - images normally included with the agreement"


IMAGE_PROVIDERS: tuple[type[NotConnectedImageProvider], ...] = (
    ManufacturerImageProvider,
    RetailerFeedImageProvider,
)


def image_integration_status() -> list[dict[str, str | bool]]:
    return [
        {"source": provider.name, "connected": provider.connected, "route": provider.licence_route}
        for provider in IMAGE_PROVIDERS
    ]
