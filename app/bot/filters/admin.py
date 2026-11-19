"""Admin authorization.

The only source of truth is ``ADMIN_TELEGRAM_IDS`` from the environment. The
filter is attached to the admin router's *observers*, so it guards every admin
message handler and every admin callback handler at once - a forged callback
payload from a normal user is rejected before any handler code runs.
"""

from __future__ import annotations

import logging

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    """Passes only for Telegram IDs listed in ``ADMIN_TELEGRAM_IDS``."""

    async def __call__(
        self,
        event: TelegramObject,
        event_from_user: TgUser | None = None,
        settings: Settings | None = None,
    ) -> bool:
        if event_from_user is None:
            return False

        admin_ids = (settings or get_settings()).admin_ids
        if not admin_ids:
            # An unconfigured admin list must not mean "everyone is an admin".
            return False

        allowed = event_from_user.id in admin_ids
        if not allowed:
            logger.info("Rejected admin access for telegram_id=%s", event_from_user.id)
        return allowed
