"""Migrations are the source of truth for the schema - keep them honest."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.config import get_settings
from app.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    database = tmp_path / "migrations_check.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    get_settings.cache_clear()

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["configure_logger"] = False
    config.attributes["database_path"] = database

    yield config

    get_settings.cache_clear()


def test_migrations_produce_the_model_schema(alembic_config: Config) -> None:
    """Fails when a model changed but no migration was generated."""
    command.upgrade(alembic_config, "head")

    database: Path = alembic_config.attributes["database_path"]
    engine = sa.create_engine(f"sqlite:///{database}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "render_as_batch": True}
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == [], f"models and migrations diverged: {differences}"


def test_downgrade_to_base_is_reversible(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    database: Path = alembic_config.attributes["database_path"]
    engine = sa.create_engine(f"sqlite:///{database}")
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert tables <= {"alembic_version"}
