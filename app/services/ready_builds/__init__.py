"""Ready-build catalogue.

Sits above the recommendation engine: it uses the engine and the component
catalogue, and nothing below imports it. Keeping it out of
``app.services.catalog`` avoids an import cycle.
"""

from app.services.ready_builds.catalogue import (
    RECIPES,
    Category,
    ReadyBuildDraft,
    Recipe,
    generate_catalogue,
    requirements_for,
)

__all__ = [
    "RECIPES",
    "Category",
    "ReadyBuildDraft",
    "Recipe",
    "generate_catalogue",
    "requirements_for",
]
