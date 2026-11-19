"""Component catalogue: loading, indexing and lookup.

Seed data lives in JSON under ``app/data/components`` so the catalogue can grow
to thousands of parts without touching a line of Python. Everything is
validated on load - a malformed entry raises here, never halfway through
building a customer's PC.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.domain.components import Component, ComponentCategory, parse_component

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[2] / "data" / "components"


class CatalogError(RuntimeError):
    """Raised when the seed data cannot be trusted."""


class Catalog:
    """An immutable, indexed view over the component seed data."""

    def __init__(self, components: Iterable[Component]) -> None:
        self._by_id: dict[str, Component] = {}
        self._by_category: dict[ComponentCategory, list[Component]] = {}

        for component in components:
            if component.id in self._by_id:
                raise CatalogError(f"duplicate component id: {component.id}")
            self._by_id[component.id] = component
            self._by_category.setdefault(component.category, []).append(component)

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Component]:
        return iter(self._by_id.values())

    def __contains__(self, component_id: object) -> bool:
        return component_id in self._by_id

    def get(self, component_id: str) -> Component | None:
        return self._by_id.get(component_id)

    def require(self, component_id: str) -> Component:
        component = self._by_id.get(component_id)
        if component is None:
            raise CatalogError(f"unknown component: {component_id}")
        return component

    def by_category(self, category: ComponentCategory) -> list[Component]:
        """Available parts in a category, excluding discontinued ones."""
        return [c for c in self._by_category.get(category, []) if not c.discontinued]

    def categories(self) -> list[ComponentCategory]:
        return sorted(self._by_category)

    def counts(self) -> dict[str, int]:
        return {category.value: len(parts) for category, parts in self._by_category.items()}


def load_components(directory: Path | None = None) -> list[Component]:
    """Read and validate every ``*.json`` catalogue file in ``directory``."""
    path = directory or DEFAULT_CATALOG_DIR
    if not path.is_dir():
        raise CatalogError(f"catalogue directory not found: {path}")

    components: list[Component] = []
    for file in sorted(path.glob("*.json")):
        raw = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise CatalogError(f"{file.name}: expected a list of components")

        for index, entry in enumerate(raw):
            try:
                components.append(parse_component(entry))
            except ValidationError as exc:
                raise CatalogError(f"{file.name}[{index}]: {exc}") from exc

    if not components:
        raise CatalogError(f"no components found in {path}")

    logger.info("Loaded %s components from %s", len(components), path)
    return components


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Process-wide catalogue. Seed data is static, so loading once is enough."""
    return Catalog(load_components())
