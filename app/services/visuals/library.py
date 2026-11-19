"""The Visual Library: one persistent picture per thing the bot can show.

Every visualiser (builds, products, future accessories) describes *what* it
wants as a :class:`VisualRequest` and asks the library. The library owns the
rules that protect the API balance:

    request  -> find by fingerprint (exact render)
             -> else find a valid render of the same identity (older prompt
                version): reuse it, 0 API calls
             -> else, if generation is allowed: take the per-fingerprint lock,
                re-check (a concurrent request may have just rendered it),
                make ONE paid call (one retry on a transient error, never more
                than ``max_attempts`` per fingerprint), save file + row +
                ledger
             -> a failed forced re-render keeps the previous picture

Nothing here ever deletes a successful visual. Re-rendering the same
fingerprint moves the old file into ``history`` and keeps it on disk.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.build_visualization import Visual, VisualEventKind, VisualizationStatus
from app.db.repositories.visualization_repo import VisualizationRepository
from app.services.media.ai_visual import ImageGenerator, VisualPrompt
from app.services.media.paths import AI_IMAGE_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisualRequest:
    """Everything the library needs to find or render one visual."""

    entity_type: str
    entity_id: str
    identity_key: str
    fingerprint: str
    prompt: VisualPrompt
    model: str
    prompt_version: str
    provider: str
    preset_key: str = ""
    components: dict = field(default_factory=dict)
    references: Sequence[Path] = ()
    entity_slug: str | None = None
    category: str | None = None
    build_id: int | None = None
    ready_build_id: int | None = None


@dataclass(slots=True)
class VisualizationResult:
    status: str
    path: Path | None = None
    record: Visual | None = None
    cache_hit: bool = False
    error: str | None = None
    spec: object | None = None
    fingerprint: str | None = None
    api_calls: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == VisualizationStatus.READY and self.path is not None


STATUS_DISABLED = "disabled"
STATUS_MISSING = "missing"


class VisualLibrary:
    """Persistent, deduplicated store of visuals plus the single way to render one."""

    #: One lock per fingerprint: concurrent identical requests share one render.
    _locks: ClassVar[dict[str, asyncio.Lock]] = {}
    #: One paid request at a time per process, with a little spacing.
    _api_lock: ClassVar[asyncio.Lock | None] = None
    _last_call: ClassVar[float] = 0.0
    MIN_INTERVAL_SECONDS: ClassVar[float] = 1.0

    def __init__(
        self,
        session: AsyncSession,
        generator: ImageGenerator,
        *,
        output_dir: Path = AI_IMAGE_DIR,
        max_attempts: int = 2,
        timeout_seconds: float = 90.0,
        cost_per_call_usd: Decimal = Decimal("0.04"),
        enabled: bool = True,
        min_interval_seconds: float | None = None,
    ) -> None:
        self._session = session
        self._min_interval = (
            min_interval_seconds if min_interval_seconds is not None else self.MIN_INTERVAL_SECONDS
        )
        self._repo = VisualizationRepository(session)
        self._generator = generator
        self._output_dir = output_dir
        self._max_attempts = max(1, max_attempts)
        self._timeout = timeout_seconds
        self._cost = cost_per_call_usd
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled and self._generator.enabled

    @property
    def repository(self) -> VisualizationRepository:
        return self._repo

    # --- lookups (free) --------------------------------------------------------

    async def find_by_fingerprint(self, fingerprint: str) -> Visual | None:
        return await self._repo.get_by_fingerprint(fingerprint)

    async def find(self, identity_key: str, fingerprint: str) -> tuple[Visual | None, str]:
        """``(visual, how)``: exact render, an older-version render of the same
        identity (``"outdated"``), or nothing. Only usable visuals count."""
        row = await self._repo.get_by_fingerprint(fingerprint)
        if row is not None and row.is_ready and _file_ok(row):
            return row, "exact"
        other = await self._repo.find_valid_by_identity(identity_key)
        if other is not None and _file_ok(other):
            return other, "outdated"
        return None, "missing"

    async def get(self, request: VisualRequest) -> Visual | None:
        found, _ = await self.find(request.identity_key, request.fingerprint)
        return found

    async def mark_used(self, visual: Visual) -> None:
        await self._repo.touch(visual)

    async def get_telegram_file_id(self, visual: Visual) -> str | None:
        return visual.telegram_file_id

    async def set_telegram_file_id(self, visual: Visual, file_id: str | None) -> None:
        await self._repo.set_file_id(visual, file_id)

    async def invalidate(self, visual: Visual, reason: str) -> None:
        await self._repo.invalidate(visual, reason)

    async def stats(self) -> dict:
        return await self._repo.stats()

    # --- the one way to render -----------------------------------------------------

    async def get_or_generate(
        self,
        request: VisualRequest,
        *,
        force: bool = False,
        allow_generation: bool = True,
    ) -> VisualizationResult:
        repo = self._repo
        await repo.record_event(VisualEventKind.REQUEST, request.entity_type, request.fingerprint)

        if not force:
            found, how = await self.find(request.identity_key, request.fingerprint)
            if found is not None:
                await repo.touch(found)
                await repo.record_event(
                    VisualEventKind.CACHE_HIT, request.entity_type, found.fingerprint
                )
                return VisualizationResult(
                    status=VisualizationStatus.READY,
                    path=Path(found.image_path or ""),
                    record=found,
                    cache_hit=True,
                    fingerprint=found.fingerprint,
                    extra={"version": how},
                )

        row = await repo.get_by_fingerprint(request.fingerprint)
        if not allow_generation:
            return VisualizationResult(
                status=STATUS_MISSING, record=row, fingerprint=request.fingerprint
            )
        if not self.enabled:
            return VisualizationResult(
                status=STATUS_DISABLED,
                record=row,
                fingerprint=request.fingerprint,
                error="AI visualisation disabled or no API key",
            )
        if (
            row is not None
            and row.status == VisualizationStatus.FAILED
            and not force
            and row.attempts >= self._max_attempts
        ):
            return VisualizationResult(
                status=VisualizationStatus.FAILED,
                record=row,
                fingerprint=request.fingerprint,
                error=f"gave up after {row.attempts} attempts: {row.error}",
            )

        lock = self._locks.setdefault(request.fingerprint, asyncio.Lock())
        async with lock:
            # Someone else may have rendered it while we waited for the lock.
            if not force:
                found, how = await self.find(request.identity_key, request.fingerprint)
                if found is not None:
                    await repo.record_event(
                        VisualEventKind.CACHE_HIT, request.entity_type, found.fingerprint
                    )
                    return VisualizationResult(
                        status=VisualizationStatus.READY,
                        path=Path(found.image_path or ""),
                        record=found,
                        cache_hit=True,
                        fingerprint=found.fingerprint,
                        extra={"version": how},
                    )
            return await self._render(request, force=force)

    async def regenerate(self, request: VisualRequest) -> VisualizationResult:
        """Explicit re-render; the previous picture survives a failure."""
        return await self.get_or_generate(request, force=True)

    async def _render(self, request: VisualRequest, *, force: bool) -> VisualizationResult:
        repo = self._repo
        row = await repo.get_by_fingerprint(request.fingerprint)
        previous: dict | None = None
        previous_path: str | None = None
        if row is not None and row.status == VisualizationStatus.READY and row.image_path:
            previous_path = row.image_path
            previous = {
                "image_path": row.image_path,
                "telegram_file_id": row.telegram_file_id,
                "prompt_version": row.prompt_version,
                "prompt_hash": row.prompt_hash,
                "model": row.model,
                "created_at": row.updated_at.isoformat() if row.updated_at else None,
                "replaced_at": datetime.now(UTC).isoformat(),
            }

        row = await repo.start(
            request.fingerprint,
            identity_key=request.identity_key,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            entity_slug=request.entity_slug,
            category=request.category,
            components=request.components,
            preset_key=request.preset_key,
            provider=request.provider,
            model=request.model,
            prompt_version=request.prompt_version,
            prompt_hash=request.prompt.key,
            prompt_text=request.prompt.text,
            references_used=bool(request.references),
            build_id=request.build_id,
            ready_build_id=request.ready_build_id,
        )
        # Release the write lock while the API works: a render takes up to a
        # minute and other customers must keep ordering meanwhile.
        await self._session.commit()

        calls = 0
        started = time.monotonic()
        png: bytes | None = None
        error: str | None = None
        spent = Decimal(0)
        while True:
            calls += 1
            spent += self._cost
            await repo.record_event(
                VisualEventKind.API_CALL, request.entity_type, request.fingerprint, self._cost
            )
            png, error, transient = await self._call_generator(
                request.prompt.text, request.references
            )
            if png is not None:
                break
            if transient and row.attempts < self._max_attempts:
                row.attempts += 1
                await asyncio.sleep(2.0)
                continue
            break

        if png is None:
            await repo.mark_failed(row, error or "unknown error", cost_usd=spent)
            if previous_path and Path(previous_path).is_file():
                await repo.restore_previous(row, previous_path)
            await repo.record_event(
                VisualEventKind.FAILED, request.entity_type, request.fingerprint
            )
            await self._session.commit()
            logger.warning("Visual %s failed: %s", request.fingerprint, error)
            return VisualizationResult(
                status=VisualizationStatus.FAILED,
                record=row,
                fingerprint=request.fingerprint,
                error=error,
                api_calls=calls,
                path=Path(previous_path) if previous_path else None,
                extra={"kept_previous": bool(previous_path)},
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        # Never overwrite an earlier render: versioned file names, old files stay.
        suffix = f"-v{row.attempts}" if previous_path else ""
        path = self._output_dir / f"ai-{request.fingerprint}{suffix}.png"
        if path.exists() and previous_path and Path(previous_path) == path:
            path = self._output_dir / f"ai-{request.fingerprint}-{int(time.time())}.png"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(png)
        tmp.replace(path)
        await repo.mark_ready(
            row,
            str(path),
            seconds=time.monotonic() - started,
            previous=previous,
            cost_usd=spent,
        )
        await repo.record_event(VisualEventKind.GENERATED, request.entity_type, request.fingerprint)
        await self._session.commit()
        logger.info(
            "Visual %s (%s) rendered in %.1fs, %s call(s)",
            request.fingerprint,
            request.entity_type,
            time.monotonic() - started,
            calls,
        )
        return VisualizationResult(
            status=VisualizationStatus.READY,
            path=path,
            record=row,
            fingerprint=request.fingerprint,
            api_calls=calls,
        )

    async def _call_generator(
        self, prompt: str, references: Sequence[Path]
    ) -> tuple[bytes | None, str | None, bool]:
        if VisualLibrary._api_lock is None:
            VisualLibrary._api_lock = asyncio.Lock()
        async with VisualLibrary._api_lock:
            gap = time.monotonic() - VisualLibrary._last_call
            if gap < self._min_interval:
                await asyncio.sleep(self._min_interval - gap)
            VisualLibrary._last_call = time.monotonic()
            try:
                png = await asyncio.wait_for(
                    asyncio.to_thread(self._generator.generate_png, prompt, tuple(references)),
                    timeout=self._timeout + 10,
                )
            except TimeoutError:
                # Ambiguous: the API may have produced (and billed) the image.
                # Fail terminally rather than risk a duplicate paid call.
                return None, f"timed out after {self._timeout:.0f}s (not retried)", False
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Image generator raised")
                return None, f"{type(exc).__name__}: {exc}"[:300], False
        if png is None:
            error = getattr(self._generator, "last_error", None) or "generator returned nothing"
            transient = bool(getattr(self._generator, "last_error_transient", False))
            return None, error, transient
        return png, None, False

    @classmethod
    def reset_locks(cls) -> None:
        """Tests only: forget per-fingerprint locks and the API spacing."""
        cls._locks.clear()
        cls._api_lock = None
        cls._last_call = 0.0


def _file_ok(row: Visual) -> bool:
    return bool(row.image_path) and Path(row.image_path or "").is_file()
