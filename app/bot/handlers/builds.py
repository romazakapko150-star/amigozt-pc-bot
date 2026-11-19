from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import MenuAction, MenuCB
from app.bot.keyboards.common import back_to_menu_kb
from app.bot.utils import safe_edit
from app.db.models import Build, User
from app.db.repositories import BuildRepository
from app.domain.enums import Purpose
from app.i18n import t

router = Router(name="builds")

MAX_LISTED = 10


def _render_list(builds: list[Build], lang: str) -> str:
    if not builds:
        return t(lang, "mybuilds.empty")

    lines = [t(lang, "mybuilds.title"), ""]
    for index, build in enumerate(builds, start=1):
        try:
            purpose = t(lang, f"purpose.{Purpose(build.purpose or '').value}")
        except ValueError:
            purpose = "-"
        lines.append(
            t(
                lang,
                "mybuilds.item",
                index=index,
                purpose=purpose,
                budget=build.budget_pln or "-",
                date=build.created_at.strftime("%d.%m.%Y"),
            )
        )
    return "\n".join(lines)


async def _fetch(session: AsyncSession, user: User | None) -> list[Build]:
    if user is None:
        return []
    return await BuildRepository(session).list_for_user(user.id, limit=MAX_LISTED)


@router.message(Command("mybuilds"))
async def cmd_my_builds(
    message: Message, session: AsyncSession, lang: str, user: User | None = None
) -> None:
    builds = await _fetch(session, user)
    await message.answer(_render_list(builds, lang), reply_markup=back_to_menu_kb(lang))


@router.callback_query(MenuCB.filter(F.action == MenuAction.MYBUILDS))
async def show_my_builds(
    callback: CallbackQuery, session: AsyncSession, lang: str, user: User | None = None
) -> None:
    builds = await _fetch(session, user)
    await safe_edit(callback, _render_list(builds, lang), back_to_menu_kb(lang))
    await callback.answer()
