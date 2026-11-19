from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Settings are validated at import time in some modules; make sure the test
# process never depends on a developer's real .env file.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:TEST-TOKEN-FOR-UNIT-TESTS-ONLY-XX")
# Environment variables win over .env, so this pins the admin list for tests
# regardless of what the developer has configured locally.
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "")
# Tests must never reach a paid image API, whatever key the developer keeps in
# .env: environment variables override .env, so this forces the AI path off.
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_VISUALIZATION_ENABLED"] = "false"

from app.bot.dispatcher import create_dispatcher
from app.config import Settings
from app.db.models import Base
from tests.fake_telegram import ADMIN_USER_ID, FAKE_TOKEN


@pytest.fixture(scope="session")
def bot_engine():
    """One shared in-memory database for the whole dispatcher session.

    ``StaticPool`` keeps every session on the same connection - otherwise each
    new connection would get its own empty ``:memory:`` database.
    """
    return create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)


@pytest.fixture(scope="session")
def bot_session_factory(bot_engine):
    return async_sessionmaker(bot_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def dispatcher(bot_session_factory):
    """The one dispatcher this process may build - aiogram allows no second."""
    settings = Settings(  # type: ignore[call-arg]
        telegram_bot_token=FAKE_TOKEN,
        admin_telegram_ids=str(ADMIN_USER_ID),
    )
    return create_dispatcher(settings, bot_session_factory)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Isolated in-memory database, one per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.fixture(autouse=True)
def _fresh_brand_state() -> None:
    """The brand cooldown is per process; tests must not see each other's.

    The file-id cache under ``media/`` belongs to the running bot: tests
    must not inherit a real Telegram id (they would assert on an upload
    that never happens) nor write their fake ids into it.
    """
    from app.services.media.brand import get_brand_assets

    assets = get_brand_assets()
    assets.use_cache_file(None)
    assets.reset()


@pytest.fixture
def gaming_answers() -> dict:
    return {
        "budget_pln": 6000,
        "purpose": "gaming",
        "games": ["cs2", "cyberpunk"],
        "resolution": "1440p",
        "target_fps": "144",
        "priority": "price_performance",
        "aesthetics": "white_rgb",
        "wifi": True,
        "bluetooth": True,
        "storage_gb": 2000,
        "ram_gb": 32,
        "cpu_brand": "amd",
        "gpu_brand": "nvidia",
    }
