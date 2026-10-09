"""ИИ-консультант для Telegram.

Отвечает клиентам по материалам из knowledge.md, ничего не выдумывает,
собирает заявки и пересылает их менеджеру, пишет журнал диалогов.
"""
import asyncio
import csv
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from dotenv import load_dotenv

from llm import make_llm

load_dotenv()
BASE = Path(__file__).parent
BUSINESS = os.getenv("BUSINESS_NAME", "Автосервис «Мотор»")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or 0)
HISTORY_LEN = int(os.getenv("HISTORY_LEN", "6"))
GREETING = os.getenv("GREETING", "Здравствуйте! Это бот автосервиса «Мотор». Подскажу цены и сроки и запишу вас. "
                                 "Спросите своими словами или выберите кнопку ниже.")
KNOWLEDGE = (BASE / os.getenv("KNOWLEDGE_FILE", "knowledge.md")).read_text(encoding="utf-8")
LOG_FILE = BASE / "logs" / "dialogs.csv"
NO_DATA = "НЕТ_ДАННЫХ"

SYSTEM_PROMPT = (
    f"Ты вежливый помощник компании {BUSINESS}. Отвечай клиентам на «вы», коротко и по делу, в 1–4 предложениях. "
    "Используй только сведения из раздела «Материалы». Не придумывай цены, сроки, акции и услуги, которых там нет. "
    f"Если ответа в материалах нет или вопрос не по теме, ответь ровно одним словом: {NO_DATA}. "
    "Если клиент хочет записаться, предложи нажать кнопку «Записаться».\n\n"
    f"Материалы:\n{KNOWLEDGE}"
)

BTN_PRICES, BTN_BOOK, BTN_MANAGER, BTN_CANCEL = "Цены и услуги", "Записаться", "Связаться с менеджером", "Отмена"
MAIN_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_PRICES), KeyboardButton(text=BTN_BOOK)],
                                        [KeyboardButton(text=BTN_MANAGER)]], resize_keyboard=True)
CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)
PHONE_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Поделиться номером", request_contact=True)],
                                         [KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)
LEAD_INLINE = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Оставить заявку", callback_data="lead")]])

router = Router()
llm = make_llm(os.getenv("LLM_PROVIDER", "fake"))
history: dict[int, list[dict]] = {}


class Lead(StatesGroup):
    name = State()
    phone = State()
    details = State()


def log_dialog(user_id, question, answer):
    LOG_FILE.parent.mkdir(exist_ok=True)
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if new:
            w.writerow(["Время", "Пользователь", "Вопрос", "Ответ"])
        w.writerow([datetime.now().strftime("%d.%m.%Y %H:%M"), user_id, question, answer])


async def ask_llm(user_id, question):
    past = history.get(user_id, [])[-HISTORY_LEN:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *past, {"role": "user", "content": question}]
    answer = (await asyncio.to_thread(llm.complete, messages)).strip()
    history[user_id] = [*past, {"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return answer


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(GREETING, reply_markup=MAIN_KB)


@router.message(Command("id"))
async def show_id(message: Message):
    await message.answer(f"ID этого чата: {message.chat.id}")


@router.message(F.text == BTN_CANCEL)
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Хорошо, отменил. Чем ещё помочь?", reply_markup=MAIN_KB)


async def start_lead(message: Message, state: FSMContext):
    await state.set_state(Lead.name)
    await message.answer("Как к вам обращаться?", reply_markup=CANCEL_KB)


@router.message(F.text.in_({BTN_BOOK, BTN_MANAGER}))
async def lead_button(message: Message, state: FSMContext):
    await start_lead(message, state)


@router.callback_query(F.data == "lead")
async def lead_inline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_lead(callback.message, state)


@router.message(Lead.name, F.text)
async def lead_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Lead.phone)
    await message.answer("Оставьте номер телефона или нажмите «Поделиться номером».", reply_markup=PHONE_KB)


@router.message(Lead.phone)
async def lead_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else (message.text or "")
    if len(re.sub(r"\D", "", phone)) < 10:
        await message.answer("Похоже, в номере не хватает цифр. Попробуйте ещё раз.", reply_markup=PHONE_KB)
        return
    await state.update_data(phone=phone)
    await state.set_state(Lead.details)
    await message.answer("Что нужно сделать и какая у вас машина? Например: замена масла, Kia Rio 2018.",
                         reply_markup=CANCEL_KB)


@router.message(Lead.details, F.text)
async def lead_details(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    user = message.from_user
    who = f"@{user.username}" if user.username else f"id {user.id}"
    text = (f"Новая заявка\nИмя: {data['name']}\nТелефон: {data['phone']}\n"
            f"Запрос: {message.text.strip()}\nTelegram: {who}")
    if ADMIN_CHAT_ID:
        await bot.send_message(ADMIN_CHAT_ID, text)
    else:
        logging.warning("ADMIN_CHAT_ID не задан, заявка только в логе:\n%s", text)
    await message.answer("Спасибо! Передал заявку менеджеру, он свяжется с вами в рабочее время.",
                         reply_markup=MAIN_KB)


@router.message(F.text == BTN_PRICES)
async def prices(message: Message, bot: Bot):
    await answer_question(message, bot, "Коротко перечисли основные услуги и цены.")


@router.message(F.text)
async def question(message: Message, bot: Bot):
    await answer_question(message, bot, message.text)


async def answer_question(message: Message, bot: Bot, text: str):
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await ask_llm(message.from_user.id, text)
    except Exception:
        logging.exception("Ошибка нейросети")
        await message.answer("Сейчас не получается ответить. Попробуйте через минуту или оставьте заявку.",
                             reply_markup=LEAD_INLINE)
        return
    if NO_DATA in answer:
        reply = "Точной информации об этом у меня нет. Могу передать вопрос менеджеру, он ответит лично."
        await message.answer(reply, reply_markup=LEAD_INLINE)
    else:
        reply = answer
        await message.answer(reply)
    log_dialog(message.from_user.id, text, reply)


def build_dispatcher():
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(os.environ["BOT_TOKEN"])
    await build_dispatcher().start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
