"""Delivery of admin notifications.

Notification failures must never cost the customer their order: the lead is
already committed by the time we get here, so every send is best-effort and
each admin is delivered to independently.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from app.bot.keyboards.admin import lead_actions_kb
from app.bot.views.admin import render_notification
from app.db.models import Build, Lead, User

logger = logging.getLogger(__name__)


class AdminNotifier:
    def __init__(self, bot: Bot, admin_ids: Iterable[int]) -> None:
        self._bot = bot
        self._admin_ids = list(admin_ids)

    async def notify_new_lead(self, lead: Lead, user: User, build: Build | None) -> int:
        """Sends the lead card to every admin. Returns how many were reached."""
        if not self._admin_ids:
            logger.warning("Lead #%s created but ADMIN_TELEGRAM_IDS is empty", lead.id)
            return 0

        text = render_notification(lead, user, build)
        keyboard = lead_actions_kb(lead)

        delivered = 0
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(admin_id, text, reply_markup=keyboard)
            except TelegramForbiddenError:
                # The admin has never opened a chat with the bot, or blocked it.
                logger.warning("Admin %s cannot receive notifications (chat not started)", admin_id)
            except TelegramAPIError:
                logger.exception("Failed to notify admin %s about lead #%s", admin_id, lead.id)
            else:
                delivered += 1

        logger.info("Lead #%s delivered to %s/%s admins", lead.id, delivered, len(self._admin_ids))
        return delivered

    async def notify_text(self, text: str) -> int:
        """Best-effort plain alert to every admin (order gate blocks, stale shelf)."""
        delivered = 0
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(admin_id, text)
            except TelegramForbiddenError:
                logger.warning("Admin %s cannot receive notifications (chat not started)", admin_id)
            except TelegramAPIError:
                logger.exception("Failed to deliver an alert to admin %s", admin_id)
            else:
                delivered += 1
        return delivered
