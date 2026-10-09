"""Подключение к нейросети. Провайдер выбирается переменной LLM_PROVIDER:

gigachat  — GigaChat от Сбера (для физлиц есть бесплатный лимит);
openai    — любой OpenAI-совместимый API: YandexGPT, OpenAI и другие;
fake      — тестовый режим без ключей, чтобы проверить кнопки и заявки.
"""
import os


class FakeLLM:
    """Отвечает заготовками. Нужен, чтобы проверить бота без ключей."""

    def complete(self, messages):
        question = messages[-1]["content"].lower()
        if "масл" in question:
            return "Замена масла с фильтром — 1 500 ₽ за работу, масло можно привезти своё или купить у нас."
        if "услуг" in question or "цен" in question:
            return "Основное: замена масла — 1 500 ₽, шиномонтаж комплекта R13–R16 — 2 400 ₽, развал-схождение — 2 000 ₽."
        return "НЕТ_ДАННЫХ"


class GigaChatLLM:
    def __init__(self):
        from gigachat import GigaChat

        self.client = GigaChat(
            credentials=os.environ["GIGACHAT_CREDENTIALS"],
            scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            verify_ssl_certs=os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() == "true",
        )
        # Имена моделей у GigaChat меняются; если не задано, берём первую доступную по ключу.
        self.model = os.getenv("GIGACHAT_MODEL") or self._first_model()

    def _first_model(self):
        models = [m.id_ for m in self.client.get_models().data]
        if not models:
            raise RuntimeError("По этому ключу не доступна ни одна модель GigaChat")
        return models[0]

    def complete(self, messages):
        from gigachat.models import Chat, Messages, MessagesRole

        roles = {"system": MessagesRole.SYSTEM, "user": MessagesRole.USER, "assistant": MessagesRole.ASSISTANT}
        chat = Chat(model=self.model, temperature=0.2,
                    messages=[Messages(role=roles[m["role"]], content=m["content"]) for m in messages])
        return self.client.chat(chat).choices[0].message.content


class OpenAICompatibleLLM:
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.getenv("OPENAI_BASE_URL") or None)
        self.model = os.environ["OPENAI_MODEL"]

    def complete(self, messages):
        r = self.client.chat.completions.create(model=self.model, messages=messages, temperature=0.2)
        return r.choices[0].message.content


def make_llm(provider):
    provider = (provider or "fake").lower()
    if provider == "gigachat":
        return GigaChatLLM()
    if provider == "openai":
        return OpenAICompatibleLLM()
    return FakeLLM()
