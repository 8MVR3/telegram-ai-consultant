"""Прогон сценариев бота без сети: Telegram подменён фальшивой сессией, нейросеть — режимом fake."""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.update(BOT_TOKEN="123456:TESTTOKEN", ADMIN_CHAT_ID="999", LLM_PROVIDER="fake")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot as B  # noqa: E402
from aiogram import Bot  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User  # noqa: E402


class MockSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            self.sent.append((method.chat_id, method.text))
            return Message(message_id=len(self.sent), date=datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b""

    async def close(self):
        pass


def test_question_and_lead_flow():
    async def run():
        session = MockSession()
        bot = Bot("123456:TESTTOKEN", session=session)
        dp = B.build_dispatcher()
        user, chat = User(id=111, is_bot=False, first_name="Вася"), Chat(id=111, type="private")
        n = 0

        async def send(text=None, contact=None):
            nonlocal n
            n += 1
            msg = Message(message_id=n, date=datetime.now(), chat=chat, from_user=user, text=text, contact=contact)
            await dp.feed_update(bot, Update(update_id=n, message=msg))

        async def press(data):
            nonlocal n
            n += 1
            cq = CallbackQuery(id=str(n), from_user=user, chat_instance="x", data=data,
                               message=Message(message_id=500, date=datetime.now(), chat=chat, from_user=user, text="..."))
            await dp.feed_update(bot, Update(update_id=n, callback_query=cq))

        await send("/start")
        await send("Сколько стоит замена масла?")
        await press("lead")
        await send("Вася")
        await send("123")
        await send(contact=Contact(phone_number="+79001234567", first_name="Вася"))
        await send("Замена масла, Kia Rio 2018")
        await bot.session.close()
        return session.sent

    sent = asyncio.run(run())
    to_admin = [text for chat_id, text in sent if chat_id == 999]
    assert to_admin, "заявка не ушла менеджеру"
    assert "+79001234567" in to_admin[-1] and "Kia Rio" in to_admin[-1]
    assert any("телефон" in text.lower() for chat_id, text in sent if chat_id == 111)
