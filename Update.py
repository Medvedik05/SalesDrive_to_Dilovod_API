import json
import logging
import re

import requests

from Main import (
    DILOVOD_API_URL,
    DILOVOD_TOKEN,
    ORGANIZATIONS_MAP,
    STATUSES_MAP,
    find_product_in_dilovod,
    get_dilovod_code,
    get_dilovod_orders,
    get_crm_orders,
)


# Укажите здесь ID заказов из SalesDrive, например: [123456, 123457]
UPDATE_ORDER_IDS = [1595]
LOOKBACK_DAYS = 365


def build_update_packet(crm_order, dilovod_order):
    order_id = crm_order.get("id")

    try:
        organization_id = int(crm_order.get("organizationId", 0))
        status_id = int(crm_order.get("statusId", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("неверный ID организации или статус") from error

    firm_code = get_dilovod_code(ORGANIZATIONS_MAP, organization_id)
    state_code = get_dilovod_code(STATUSES_MAP, status_id)
    if not firm_code or not state_code:
        raise ValueError("не найдено соответствие организации или статуса в словарях")

    phone = ""
    primary_contact = crm_order.get("primaryContact")
    if isinstance(primary_contact, dict):
        phone_list = primary_contact.get("phone", [])
        if isinstance(phone_list, list) and phone_list:
            phone = str(phone_list[0])

    ttn = ""
    delivery_data = crm_order.get("ord_delivery_data")
    if isinstance(delivery_data, list) and delivery_data:
        first_delivery = delivery_data[0]
        if isinstance(first_delivery, dict):
            ttn = first_delivery.get("trackingNumber", "")

    dilovod_goods = []
    missing_skus = []
    for product in crm_order.get("products", []):
        sku = product.get("sku")
        if not sku:
            continue

        product_id = find_product_in_dilovod(sku)
        if not product_id:
            missing_skus.append(sku)
            continue

        amount = product.get("amount", 1)
        price = product.get("price", 0)
        row_sum = amount * price
        dilovod_goods.append({
            "good": product_id,
            "qty": amount,
            "price": price,
            "unit": "1103600000000001",
            "amountCur": row_sum,
            "priceAmount": row_sum,
        })

    if missing_skus:
        raise ValueError(f"товары не найдены в Діловоде: {missing_skus}")
    if not dilovod_goods:
        raise ValueError("в заказе нет товаров для обновления")

    dilovod_id = dilovod_order.get("id")
    if not dilovod_id:
        raise ValueError("у документа Діловода отсутствует внутренний ID")

    return {
        "version": "0.25",
        "key": DILOVOD_TOKEN,
        "action": "saveObject",
        "params": {
            "header": {
                "id": dilovod_id,
                "date": crm_order.get("orderTime"),
                "remark": f"[{order_id}]",
                "firm": firm_code,
                "state": state_code,
                "currency": "1101200000001001",
                "person": "1100100000000001",
                "storage": "1100700000000001",
                "deliveryMethod": "1110400000001001",
                "details": phone,
                "deliveryRemark_forDel": ttn,
            },
            "tableParts": {"tpGoods": dilovod_goods},
        },
    }


def update_dilovod_order(packet, order_id):
    try:
        response = requests.post(
            DILOVOD_API_URL,
            data={"packet": json.dumps(packet)},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        logging.error("Заказ %s: ошибка запроса к Діловоду: %s", order_id, error)
        return False

    if isinstance(result, dict) and "error" in result:
        logging.error("Заказ %s: ошибка Діловода: %s", order_id, result["error"])
        return False
    if isinstance(result, list) and result and isinstance(result[0], dict) and "error" in result[0]:
        logging.error("Заказ %s: ошибка Діловода: %s", order_id, result[0]["error"])
        return False
    if result is False:
        logging.error("Заказ %s: Діловод вернул отказ без описания ошибки", order_id)
        return False

    logging.info("Заказ %s обновлен в Діловоде", order_id)
    return True


def main():
    if not UPDATE_ORDER_IDS:
        logging.warning("Список UPDATE_ORDER_IDS пуст. Заказы не обновлялись.")
        return

    requested_ids = {str(order_id) for order_id in UPDATE_ORDER_IDS}
    crm_orders = get_crm_orders(days_back=LOOKBACK_DAYS)
    dilovod_orders = get_dilovod_orders(days_back=LOOKBACK_DAYS)
    if dilovod_orders is None:
        logging.error("Не удалось получить заказы из Діловода. Обновление отменено.")
        return

    crm_by_id = {str(order.get("id")): order for order in crm_orders}
    dilovod_by_crm_id = {}
    for order in dilovod_orders:
        match = re.search(r"\[(\d+)\]", str(order.get("remark", "")))
        if match:
            dilovod_by_crm_id.setdefault(match.group(1), []).append(order)

    packets = []
    preflight_failed = False
    for order_id in sorted(requested_ids):
        crm_order = crm_by_id.get(order_id)
        dilovod_matches = dilovod_by_crm_id.get(order_id, [])

        if not crm_order:
            logging.error(
                "Заказ %s не найден в SalesDrive за последние %s дней",
                order_id,
                LOOKBACK_DAYS,
            )
            preflight_failed = True
            continue
        if len(dilovod_matches) != 1:
            logging.error(
                "Для заказа %s найдено документов Діловода: %s; требуется ровно один",
                order_id,
                len(dilovod_matches),
            )
            preflight_failed = True
            continue

        try:
            packet = build_update_packet(crm_order, dilovod_matches[0])
        except (TypeError, ValueError) as error:
            logging.error("Заказ %s не подготовлен: %s", order_id, error)
            preflight_failed = True
            continue
        packets.append((order_id, packet))

    if preflight_failed:
        logging.error("Проверка не пройдена. Ни один заказ не обновлялся.")
        return

    for order_id, packet in packets:
        update_dilovod_order(packet, order_id)


if __name__ == "__main__":
    main()
