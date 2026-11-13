
import os
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
DOMAIN = os.getenv("DOMAIN")

DAYS_BACK = 30
LIMIT = 100

URL = f"https://{DOMAIN}.salesdrive.me/api/order/list/"

HEADERS = {
    "X-Api-Key": API_KEY,
    "Content-Type": "application/json"
}

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


def get_all_orders():

    date_from = (
        datetime.now() - timedelta(days=DAYS_BACK)
    ).strftime("%Y-%m-%d")

    params = {
        "limit": LIMIT,
        "filter[orderTime][from]": date_from
    }

    all_orders = []
    page = 1

    while True:

        params["page"] = page

        response = requests.get(
            URL,
            headers=HEADERS,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()
        orders = data.get("data", [])

        if not orders:
            break

        all_orders.extend(orders)

        print(
            f"Страница {page}: "
            f"{len(orders)} заказов | "
            f"Всего загружено: {len(all_orders)}"
        )

        meta = data.get("meta", {})
        total_pages = meta.get("totalPages")

        if total_pages is not None and page >= int(total_pages):
            break

        if len(orders) < LIMIT:
            break

        page += 1
        time.sleep(10)

    return all_orders


def filter_orders(orders):

    result = []

    allowed_orgs = set(ORGANIZATIONS_MAP.values())
    allowed_statuses = set(STATUSES_MAP.values())
    allowed_payments = set(PAYMENT_METHODS_MAP.values())

    for order in orders:

        org_id = order.get("organizationId")
        status_id = order.get("statusId")
        payment_id = order.get("payment_method")

        if (
            org_id in allowed_orgs
            and status_id in allowed_statuses
            and payment_id in allowed_payments
            and status_id not in IGNORED_STATUSES
        ):
            result.append(order)

    return result


def main():

    print("Загрузка заказов SalesDrive...\n")

    orders = get_all_orders()

    unique_ids = {
        order.get("id")
        for order in orders
    }

    filtered_orders = filter_orders(orders)

    print("\n" + "=" * 55)
    print("ИТОГИ")
    print("=" * 55)

    print(f"Всего получено со всех страниц: {len(orders)}")
    print(f"Уникальных заказов:             {len(unique_ids)}")
    print(f"Дубликатов в ответе:             {len(orders) - len(unique_ids)}")
    print(f"После применения фильтров:       {len(filtered_orders)}")

    print("=" * 55)


if __name__ == "__main__":
    main()
