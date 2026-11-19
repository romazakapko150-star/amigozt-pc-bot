# AmigoZT PC

Telegram bot that configures custom PCs: the user answers plain questions
(budget, games, resolution, looks) and the system does the technical work —
picking compatible parts, optimising price/performance and pricing the build in
PLN for the Polish market.

Bot: [@AmigoPC_bot](https://t.me/AmigoPC_bot) · Market: Poland · Currency: PLN
· Languages: RU / PL / EN

## Status

**Phase 1 complete** — bot, menu, full configurator, persistence, analytics.
Component database, compatibility engine and build generation land in Phase 2.

## Quick start

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN` from
[@BotFather](https://t.me/BotFather). The token is read from `.env` only — it is
never hardcoded, never logged, and `.env` is git-ignored.

```bash
.venv/Scripts/alembic.exe upgrade head
```

```bash
.venv/Scripts/python.exe -m app.main
```

## Checks

```bash
.venv/Scripts/python.exe -m pytest -q
```

```bash
.venv/Scripts/ruff.exe check app tests
```

```bash
.venv/Scripts/mypy.exe app
```

## Architecture

```
app/
  config.py            settings from .env (secrets as SecretStr)
  logging_setup.py     log filter that redacts anything token-shaped
  main.py              entry point: engine -> bot -> dispatcher -> polling
  domain/              pure models: enums, labels, BuildRequirements
  bot/
    flows/             the question graph (ordering, skips, back history)
    handlers/          thin glue: parse -> validate -> store -> next step
    keyboards/         inline keyboards
    views/             message rendering (HTML-escaped)
    middlewares/       throttling -> db session -> user/language
  db/
    models/            SQLAlchemy ORM
    repositories/      data access, one class per aggregate
  services/analytics/  anonymised product events
  i18n/                one dict per locale (ru, pl, en)
migrations/            Alembic; the single source of truth for the schema
tests/                 unit + end-to-end handler tests
```

**Why this shape.** The configurator's ordering lives in `bot/flows` as data,
not control flow, so the whole conversation graph is unit-testable without a
Telegram server and adding a question is a one-line change. `domain/` has no
aiogram or SQLAlchemy imports, so the compatibility engine and optimiser built
on top of it in Phase 2 stay pure and cheap to test.

**Stack.** aiogram 3 (async, built-in FSM), SQLAlchemy 2 async + Alembic,
Pydantic v2, pytest/ruff/mypy. `DATABASE_URL` defaults to SQLite so the bot runs
with no external services; point it at PostgreSQL (`postgresql+asyncpg://…`) for
production — install with `pip install -e ".[postgres]"`.

## Conversation flow

`/start` → main menu → configurator:

budget → purpose → *games* → resolution → *target FPS* → priority → looks →
Wi-Fi/Bluetooth → storage → RAM → CPU brand → GPU brand → summary

Italic steps are asked only for gaming purposes. "⬅️ Back" and "❌ Cancel" work
at every step; the "🎮 Gaming PC" entry pre-fills the purpose and skips that
question.

## Data model

| Table | Purpose |
| --- | --- |
| `users` | telegram_id, username, chosen language |
| `builds` | requirements JSON + components JSON + denormalised filter columns |
| `leads` | purchase requests (Phase 6) |
| `analytics_events` | anonymised funnel events — no message text is stored |

## Roadmap

1. ✅ Bot, menu, configurator, persistence, analytics
2. Component database, compatibility engine, build generator
3. Pricing, build cards, saved builds
4. AI assistant (natural language, explanations)
5. Real store prices (x-kom, Morele, Media Expert, …)
6. Orders and leads
7. AI PC visualisation
8. Admin dashboard

## Security notes

- Secrets live in `.env` only; `Settings` wraps them in `SecretStr`.
- `SecretRedactingFilter` scrubs anything token-shaped from every log record,
  including request URLs built by aiogram.
- Per-user token-bucket throttling runs before any database work.
- All user-supplied text is escaped before being rendered into HTML messages.
- Users never see tracebacks; the developer log gets the full exception.
