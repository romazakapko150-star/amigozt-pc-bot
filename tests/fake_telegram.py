"""A Telegram server stand-in.

Lets the real ``Dispatcher`` - real routers, real middlewares, real FSM - run
against recorded API calls instead of the network, so handler behaviour can be
asserted end to end without a bot token.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, PhotoSize, Update
from aiogram.types import User as TgUser

FAKE_TOKEN = "123456789:FAKE-TOKEN-USED-ONLY-BY-THE-TEST-SUITE"

BOT_ID = 123456789
USER_ID = 555_000_111
CHAT_ID = 555_000_111

#: A separate identity used to exercise the admin-only handlers.
ADMIN_USER_ID = 900_000_777


class RecordingSession(BaseSession):
    """Records every outgoing API call and answers with a plausible result."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.calls.append(method)
        return _canned_response(method, bot)

    async def stream_content(  # type: ignore[override]
        self,
        url: str,
        headers: dict | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""

    # --- assertions helpers ---

    def of_type(self, name: str) -> list[TelegramMethod[Any]]:
        return [call for call in self.calls if type(call).__name__ == name]

    @property
    def sent_messages(self) -> list[TelegramMethod[Any]]:
        return self.of_type("SendMessage")

    @property
    def edits(self) -> list[TelegramMethod[Any]]:
        return self.of_type("EditMessageText")

    @property
    def photos(self) -> list[TelegramMethod[Any]]:
        return self.of_type("SendPhoto")

    def _outgoing(self) -> list[TelegramMethod[Any]]:
        """Everything a customer would read: texts, captions and their edits."""
        return [call for call in self.calls if type(call).__name__ in _READABLE]

    @property
    def last_text(self) -> str:
        outgoing = self._outgoing()
        assert outgoing, "the bot sent nothing"
        return _text_of(outgoing[-1])

    @property
    def last_markup(self) -> InlineKeyboardMarkup | None:
        outgoing = self._outgoing()
        assert outgoing, "the bot sent nothing"
        markup = getattr(outgoing[-1], "reply_markup", None)
        return markup if isinstance(markup, InlineKeyboardMarkup) else None

    def clear(self) -> None:
        self.calls.clear()


_READABLE = {"SendMessage", "EditMessageText", "SendPhoto", "EditMessageCaption"}

#: What Telegram would hand back for any uploaded photo.
FAKE_PHOTO_FILE_ID = "AgACAgIAAxkDAAIB-fake-brand-file-id"


def _text_of(method: TelegramMethod[Any]) -> str:
    if type(method).__name__ in {"SendPhoto", "EditMessageCaption"}:
        return str(getattr(method, "caption", "") or "")
    return str(getattr(method, "text", ""))


def _canned_response(method: TelegramMethod[Any], bot: Bot | None = None) -> Any:
    name = type(method).__name__
    if name == "GetMe":
        return TgUser(id=BOT_ID, is_bot=True, first_name="AmigoZT PC", username="AmigoPC_bot")
    if name in {"SendMessage", "EditMessageText"}:
        result: Message = _message(text=str(getattr(method, "text", "")))
    elif name == "SendPhoto":
        result = _photo_message(caption=str(getattr(method, "caption", "") or ""))
    else:
        return True
    # Real responses come back bound to the bot, so handlers can call
    # ``message.delete()`` / ``edit_text()`` on what they just sent.
    return result.as_(bot) if bot is not None else result


def _message(text: str = "", message_id: int = 1) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="private"),
        from_user=TgUser(id=BOT_ID, is_bot=True, first_name="AmigoZT PC"),
        text=text,
    )


def _photo_message(caption: str = "", message_id: int = 2) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="private"),
        from_user=TgUser(id=BOT_ID, is_bot=True, first_name="AmigoZT PC"),
        caption=caption,
        photo=[
            PhotoSize(
                file_id=FAKE_PHOTO_FILE_ID, file_unique_id="fake-unique", width=1254, height=1254
            )
        ],
    )


def make_bot() -> Bot:
    """A Bot wired to the recording session - no network, no real token."""
    return Bot(
        token=FAKE_TOKEN,
        session=RecordingSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def user(language_code: str = "ru", user_id: int = USER_ID) -> TgUser:
    is_admin = user_id == ADMIN_USER_ID
    return TgUser(
        id=user_id,
        is_bot=False,
        first_name="Owner" if is_admin else "Roma",
        username="amigo_admin" if is_admin else "amigo_tester",
        language_code=language_code,
    )


def message_update(
    text: str,
    update_id: int = 1,
    language_code: str = "ru",
    user_id: int = USER_ID,
) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"),
            from_user=user(language_code, user_id),
            text=text,
        ),
    )


def callback_update(
    data: str,
    update_id: int = 1,
    language_code: str = "ru",
    bot: Bot | None = None,
    user_id: int = USER_ID,
) -> Update:
    carrier = Message(
        message_id=100,
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=TgUser(id=BOT_ID, is_bot=True, first_name="AmigoZT PC"),
        text="previous question",
    )
    if bot is not None:
        carrier = carrier.as_(bot)

    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=user(language_code, user_id),
            chat_instance="test-chat-instance",
            message=carrier,
            data=data,
        ),
    )
