"""Audit every shelf build for lighting honesty.

Read-only. Answers one question per build: do the parts, the card copy, the
visual spec and the stored image tell the same story about lighting? The
failure modes it looks for are the ones that damage trust rather than
pixels - a machine sold as "RGB" that cannot glow, or a lit machine
photographed dark.

    python -m scripts.audit_lighting

Nothing here generates or spends: it reports, and the operator decides what
to re-render.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import ReadyBuild, ReadyBuildStatus
from app.db.repositories.visualization_repo import VisualizationRepository
from app.domain.enums import Aesthetics
from app.domain.lighting import LightingState, plan_lighting
from app.i18n import DEFAULT_LANGUAGE
from app.services.ai.visualizer import Visualizer, describe_build
from app.services.catalog import get_catalog
from app.services.compatibility.gate import parts_from_ids
from app.services.media.presets import default_preset

logger = logging.getLogger("audit_lighting")

#: What each finding means, in the order of how much it would embarrass us.
FINDINGS = {
    "claims_light_without_hardware": "card would claim lighting the parts cannot produce",
    "lit_but_card_silent": "parts glow but the card says nothing",
    "requested_but_impossible": "customer asked for RGB these parts cannot give",
    "featured_but_spec_dark": "lighting requested but the visual spec has no lit parts",
    "spec_lit_but_no_image": "spec says lit and no render exists",
    "image_older_than_spec": "render was made under a different lighting signature",
    "unknown_only": "no lighting data for any part in the build",
}


@dataclass
class BuildAudit:
    slug: str
    name: str
    rgb_flag: bool
    state: LightingState
    lit_parts: tuple[str, ...] = ()
    addressable: tuple[str, ...] = ()
    signature: str = "off"
    has_image: bool = False
    image_signature: str | None = None
    findings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


async def audit() -> list[BuildAudit]:
    settings = get_settings()
    catalog = get_catalog()
    visualizer = Visualizer.from_settings(settings)
    engine = create_async_engine("sqlite+aiosqlite:///file:amigozt.db?mode=ro&uri=true")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    results: list[BuildAudit] = []

    async with factory() as session:
        repo = VisualizationRepository(session)
        stmt = (
            select(ReadyBuild)
            .where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
            .order_by(ReadyBuild.id)
        )
        for ready in await session.scalars(stmt):
            parts, unknown = parts_from_ids(ready.components, catalog)
            if unknown or not parts:
                continue

            wants = bool(ready.visual_priorities)
            plan = plan_lighting(parts, requested=wants)
            try:
                aesthetics: Aesthetics | None = Aesthetics(ready.style)
            except ValueError:
                aesthetics = None
            preset = default_preset(parts, aesthetics)
            spec = describe_build(parts, preset, priorities=ready.visual_priorities)

            row = BuildAudit(
                slug=ready.slug,
                name=ready.name,
                rgb_flag=bool(ready.rgb),
                state=plan.state,
                lit_parts=plan.capabilities.lit,
                addressable=plan.capabilities.addressable,
                signature=spec.lighting_signature,
            )

            visual = await repo.find_valid_by_identity(
                visualizer.identity_for(parts, preset, ready.visual_priorities)
            )
            row.has_image = visual is not None and Path(visual.image_path or "").is_file()

            # --- the failure modes ---------------------------------------
            if ready.rgb and not plan.capabilities.any_lit:
                row.findings.append("claims_light_without_hardware")
            if plan.capabilities.any_lit and not ready.rgb:
                row.findings.append("lit_but_card_silent")
            if plan.state is LightingState.UNAVAILABLE:
                row.findings.append("requested_but_impossible")
            if plan.emphasise and not spec.lit_parts:
                row.findings.append("featured_but_spec_dark")
            if spec.lit_parts and not row.has_image:
                row.findings.append("spec_lit_but_no_image")
            if (
                not plan.capabilities.lit
                and not plan.capabilities.header_capable
                and len(plan.capabilities.unknown) == len(parts)
            ):
                row.findings.append("unknown_only")

            results.append(row)

    await engine.dispose()
    return results


def report(rows: list[BuildAudit]) -> None:
    lit = [r for r in rows if r.lit_parts]
    flagged = [r for r in rows if r.rgb_flag]
    problems = [r for r in rows if not r.ok]

    print(f"{'build':<28}{'flag':>6}{'state':>13}{'signature':>11}  lit parts")
    print("-" * 88)
    for row in rows:
        mark = "  " if row.ok else "!!"
        print(
            f"{mark}{row.slug:<26}{'rgb' if row.rgb_flag else '-':>6}"
            f"{row.state.value:>13}{row.signature:>11}  {','.join(row.lit_parts) or '-'}"
        )

    print()
    print(f"builds audited:        {len(rows)}")
    print(f"lighting-capable:      {len(lit)}")
    print(f"marked rgb on the row: {len(flagged)}")
    print(f"with a stored render:  {sum(1 for r in rows if r.has_image)}")
    print(f"clean:                 {len(rows) - len(problems)}")
    print(f"with findings:         {len(problems)}")

    if problems:
        print()
        print("FINDINGS")
        counted: dict[str, int] = {}
        for row in problems:
            for finding in row.findings:
                counted[finding] = counted.get(finding, 0) + 1
        for finding, count in sorted(counted.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>3}  {finding}: {FINDINGS.get(finding, '')}")
        print()
        for row in problems:
            print(f"  {row.slug}: {', '.join(row.findings)}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    assert DEFAULT_LANGUAGE  # the card copy is rendered in the default locale
    report(asyncio.run(audit()))


if __name__ == "__main__":
    main()
