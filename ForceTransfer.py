import logging
import re

import requests

from Main import (
    API_KEY,
    DOMAIN,
    get_dilovod_orders,
    mark_order_in_salesdrive,
    prepare_error_message,
    prepare_missing_products_message,
    send_to_dilovod,
    send_telegram_message,
)
from Update import build_update_packet, update_dilovod_order


# Укажите ID заказов SaleDrive, которые нужно перенести вручную.
ORDER_IDS = [1595]
DILOVOD_LOOKBACK_DAYS = 365


def get_salesdrive_order(order_id):
    url = f"https://{DOMAIN}.salesdrive.me/api/order/list/"
    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json",
    }

    response = requests.get(
        url,
        headers=headers,
        params={"filter[id]": str(order_id)},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("неожиданный формат ответа SaleDrive")

    for order in data.get("data", []):
        if str(order.get("id")) == str(order_id):
            return order
    return None


def index_dilovod_orders(dilovod_orders):
    orders_by_crm_id = {}
    for order in dilovod_orders:
        match = re.search(r"\[(\d+)\]", str(order.get("remark", "")))
        if match:
            orders_by_crm_id.setdefault(match.group(1), []).append(order)
    return orders_by_crm_id


def main():
    requested_ids = list(dict.fromkeys(str(order_id) for order_id in ORDER_IDS))
    if not requested_ids:
        logging.warning("Список ORDER_IDS пуст. Заказы не переносились.")
        return

    crm_orders = {}
    try:
        for order_id in requested_ids:
            order = get_salesdrive_order(order_id)
            if order is None:
                logging.error("Заказ %s не найден в SaleDrive. Перенос отменен.", order_id)
                return
            crm_orders[order_id] = order
    except (requests.RequestException, ValueError) as error:
        logging.error("Не удалось загрузить заказы из SaleDrive: %s. Перенос отменен.", error)
        return

    dilovod_orders = get_dilovod_orders(days_back=DILOVOD_LOOKBACK_DAYS)
    if dilovod_orders is None:
        logging.error("Не удалось проверить заказы в Діловоде. Перенос отменен.")
        return
    dilovod_orders_by_crm_id = index_dilovod_orders(dilovod_orders)

    transferred_count = 0
    for order_id in requested_ids:
        order = crm_orders[order_id]
        existing_orders = dilovod_orders_by_crm_id.get(order_id, [])
        if len(existing_orders) > 1:
            logging.error(
                "Для заказа %s найдено несколько документов Діловода (%s). Пропускаем.",
                order_id,
                len(existing_orders),
            )
            continue

        if existing_orders:
            logging.info("Заказ %s уже есть в Діловоде; обновляю его данными SaleDrive.", order_id)
            try:
                packet = build_update_packet(order, existing_orders[0])
            except (TypeError, ValueError) as error:
                logging.error("Заказ %s не подготовлен к обновлению: %s", order_id, error)
                continue

            if update_dilovod_order(packet, order_id):
                mark_order_in_salesdrive(order_id, "id_23")
                transferred_count += 1
            continue

        logging.info("Создаю заказ %s в Діловоде...", order_id)
        result = send_to_dilovod(order)

        if isinstance(result, tuple) and result[0] == "missing_products":
            send_telegram_message(prepare_missing_products_message(order_id, result[1]))
            mark_order_in_salesdrive(order_id, "id_24")
        elif result:
            mark_order_in_salesdrive(order_id, "id_23")
            transferred_count += 1
            logging.info("Заказ %s перенесен в Діловод.", order_id)
        else:
            send_telegram_message(
                prepare_error_message(order_id, "неизвестно", "Ошибка создания в Діловод")
            )
            mark_order_in_salesdrive(order_id, "id_24")

    logging.info("Перенос завершен. Успешно перенесено: %s", transferred_count)


if __name__ == "__main__":
    main()