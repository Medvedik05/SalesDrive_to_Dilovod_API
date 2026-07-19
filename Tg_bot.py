import requests
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

raw_chat_ids = os.getenv("CHAT_IDS", "")
clean_ids = raw_chat_ids.replace('[', '').replace(']', '').replace("'", "").replace('"', "").replace(" ", "")
CHAT_IDS = clean_ids.split(',') if clean_ids else []

def prepare_missing_products_message(order_id, missing_skus):
    """
    Формує спеціальне повідомлення, якщо товарів немає в Діловоді.
    """
    skus_str = "\n".join([f"• <code>{sku}</code>" for sku in missing_skus])
    message = (
        f"⚠️ <b>Відсутні товари в Діловоді (Замовлення №{order_id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ці товари є в SalesDrive, але не знайдені в Діловоді:\n"
        f"{skus_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    return message

def prepare_error_message(order_id, product_sku, error_reason="Помилка створення в Діловоді"):
    """
    Формує повідомлення про загальну помилку створення/оновлення замовлення.
    """
    message = (
        f"⚠️ <b>Помилка обробки замовлення №{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❌ <b>Причина:</b> {error_reason}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>⚠️ Потрібна термінова перевірка логів або ручна обробка.</i>"
    )
    return message

def send_telegram_message(message, chat_ids=None):
    """
    Отправляет сообщение в один или несколько чатов.
    chat_ids может быть строкой (один ID) или списком [ID1, ID2, ...].
    Если chat_ids не передан — шлет в дежурный чат.
    """
    

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"parse_mode": "HTML", "text": message}

    for chat_id in CHAT_IDS:
        try:
            payload["chat_id"] = chat_id
            response = requests.post(url, data=payload, timeout=5)
            if response.status_code != 200:
                print(f"⚠️ Ошибка отправки в чат {chat_id}: {response.text}")
        except Exception as e:
            print(f"❌ Критическая ошибка при отправке в {chat_id}: {e}")