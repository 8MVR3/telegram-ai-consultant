"""Печатает модели GigaChat, доступные по вашему ключу. Имя нужной впишите в GIGACHAT_MODEL."""
import os

from dotenv import load_dotenv
from gigachat import GigaChat

load_dotenv()
giga = GigaChat(credentials=os.environ["GIGACHAT_CREDENTIALS"],
                scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
                verify_ssl_certs=os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() == "true")
for model in giga.get_models().data:
    print(model.id_)
