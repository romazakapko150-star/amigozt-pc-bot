from app.services.recommendation.build_service import BuildOption, BuildService
from app.services.recommendation.generator import (
    BuildGenerationError,
    GeneratedBuild,
    Parts,
    PriceBook,
    generate_build,
    generate_variants,
    is_legacy_platform,
    minimum_acquisition_cost,
)
from app.services.recommendation.replacement import (
    ConflictResolution,
    Replacement,
    resolve_conflict,
    suggest_replacements,
)

__all__ = [
    "BuildGenerationError",
    "BuildOption",
    "BuildService",
    "ConflictResolution",
    "GeneratedBuild",
    "Parts",
    "PriceBook",
    "Replacement",
    "generate_build",
    "generate_variants",
    "is_legacy_platform",
    "minimum_acquisition_cost",
    "resolve_conflict",
    "suggest_replacements",
]
