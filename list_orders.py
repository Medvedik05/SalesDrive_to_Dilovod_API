
import os
import sys
import requests

from datetime import datetime, timedelta
from dotenv import load_dotenv


# ==============================
# НАСТРОЙКИ
# ==============================

load_dotenv()

API_KEY = os.getenv("API_KEY")
DOMAIN = os.getenv("DOMAIN")

DAYS_BACK = 30
LIMIT = 1000

URL = f"https://{DOMAIN}.salesdrive.me/api/order/list/"

HEADERS = {
    "X-Api-Key": API_KEY,
    "Content-Type": "application/json"
}


# ==============================
# ФИЛЬТРЫ ИЗ MAIN.PY
# ==============================

STATUSES_MAP = {
    "Новий": 1,
    "Прийнято": 2,
    "На відправку": 3,
    "Відправлений": 4,
    "Продаж": 5,
    "Відмова": 6,
    "Повернення": 7,
    "Видалений": 8,
    "Скасовано покупцем": 9,
    "дубль": 10
}

PAYMENT_METHODS_MAP = {
    "Пром-оплата": 16,
    "Післяоплата": 6,
    "Оплата частинами": 28
}

ORGANIZATIONS_MAP = {
    "Б": 3,
    "Н": 4,
    "Т": 1
}

IGNORED_STATUSES = {1, 2, 6, 7, 8, 9, 10}


# ==============================
# ПОЛУЧЕНИЕ ЗАКАЗОВ
# ==============================

def get_orders():

    date_from = (
        datetime.now() - timedelta(days=DAYS_BACK)
    ).strftime("%Y-%m-%d")

    params = {
        "limit": LIMIT,
        "filter[orderTime][from]": date_from
    }

    all_orders = []
    page = 1

    print(f"\nЗагрузка заказов с {date_from}...\n")

    while True:

        params["page"] = page

        response = requests.get(
            URL,
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Ошибка SalesDrive: "
                f"{response.status_code}\n{response.text}"
            )

        data = response.json()
        print("META:", data.get("meta"))
        print("LIMIT:", LIMIT)
        print("PAGE:", page)
        print("ORDERS:", len(data.get("data", [])))
        orders = data.get("data", [])

        if not isinstance(orders, list):
            raise RuntimeError("Некорректный формат ответа SalesDrive")

        if not orders:
            break

        all_orders.extend(orders)

        print(
            f"Страница {page}: "
            f"получено {len(orders)} заказов"
        )

        meta = data.get("meta", {})
        total_pages = meta.get("totalPages")

        if total_pages is not None:
            if page >= int(total_pages):
                break
        elif len(orders) < LIMIT:
            break

        page += 1

    print(f"\nВсего получено: {len(all_orders)}")

    return all_orders


# ==============================
# ПРИМЕНЕНИЕ ФИЛЬТРОВ
# ==============================

def filter_orders(orders):

    allowed_orgs = set(ORGANIZATIONS_MAP.values())
    allowed_statuses = set(STATUSES_MAP.values())
    allowed_payments = set(PAYMENT_METHODS_MAP.values())

    result = []

    rejected = {
        "organization": 0,
        "status": 0,
        "payment": 0,
        "ignored_status": 0
    }

    for order in orders:

        org_id = order.get("organizationId")
        status_id = order.get("statusId")
        payment_id = order.get("payment_method")

        reasons = []

        # Проверка организации
        if org_id not in allowed_orgs:
            reasons.append("organization")
            rejected["organization"] += 1

        # Проверка статуса
        if status_id not in allowed_statuses:
            reasons.append("status")
            rejected["status"] += 1

        # Проверка способа оплаты
        if payment_id not in allowed_payments:
            reasons.append("payment")
            rejected["payment"] += 1

        # Проверка исключённых статусов
        if status_id in IGNORED_STATUSES:
            reasons.append("ignored_status")
            rejected["ignored_status"] += 1

        if not reasons:
            result.append(order)

    return result, rejected


# ==============================
# ВЫВОД РЕЗУЛЬТАТА
# ==============================

def main():

    if not API_KEY or not DOMAIN:
        print("Ошибка: проверь API_KEY и DOMAIN в файле .env")
        sys.exit(1)

    try:

        orders = get_orders()

        filtered, rejected = filter_orders(orders)

        print("\n" + "=" * 65)
        print("РЕЗУЛЬТАТ ФИЛЬТРАЦИИ")
        print("=" * 65)

        print(f"Всего заказов:             {len(orders)}")
        print(f"Прошли все фильтры:        {len(filtered)}")
        print(f"Исключено:                 {len(orders) - len(filtered)}")

        print("\nПричины исключения (пересекаются):")

        for reason, count in rejected.items():
            print(f"{reason}: {count}")

        print("\n" + "=" * 65)
        print("СПИСОК ПОДХОДЯЩИХ ЗАКАЗОВ")
        print("=" * 65)

        for order in filtered:

            print(
                f"ID: {order.get('id')} | "
                f"Дата: {order.get('orderTime')} | "
                f"Организация: {order.get('organizationId')} | "
                f"Статус: {order.get('statusId')} | "
                f"Оплата: {order.get('payment_method')}"
            )

        print("\n" + "=" * 65)
        print(f"ИТОГО: {len(filtered)} заказов")
        print("=" * 65)

    except Exception as e:
        print(f"\nОШИБКА: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
