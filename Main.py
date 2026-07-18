import json
import os
import re
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# --- КЛЮЧИ И НАСТРОЙКИ ---
API_KEY = os.getenv("API_KEY")
DOMAIN = os.getenv("DOMAIN")
DILOVOD_API_URL = "https://api.dilovod.ua/api/"
DILOVOD_TOKEN = os.getenv("DILOVOD_TOKEN") 
ORGANIZATIONS_MAP = os.getenv("ORGANIZATIONS_MAP")

# --- СЛОВАРИ ДЛЯ ФИЛЬТРОВ ---

STATUSES_MAP = {
    "Новий": {
        "crm_code": 1,
        "dil_code": "1111500000000005"
    },
    "Прийнято": {
        "crm_code": 2,
        "dil_code": "1111500000000005"
    },
    "На відправку": {
        "crm_code": 3,
        "dil_code": "1111500000000005"
    },
    "Відправлений": {
        "crm_code": 4,
        "dil_code": "1111500000000008"
    },
    "Продаж": {
        "crm_code": 5,
        "dil_code": "1111500000000006"
    },
    "Відмова": {
        "crm_code": 6,
        "dil_code": "1111500000000007"
    },
    "Повернення": {
        "crm_code": 7,
        "dil_code": "1111500000000007"
    },
    "Видалений": {
        "crm_code": 8,
        "dil_code": "1111500000000007"
    },
    "Скасовано покупцем": {
        "crm_code": 9,
        "dil_code": "1111500000000007"
    },
    "дубль": {
        "crm_code": 10,
        "dil_code": "1111500000000007"
    }, 
}

PAYMENT_METHODS_MAP = {
    "Пром-оплата": {
        "crm_code": 16
    },
    "Післяоплата": {
        "crm_code": 6
    }
}

ignored_statuses = {1, 2, 6, 7, 8, 9, 10}

# --- ОСНОВНАЯ ФУНКЦИЯ ---
def get_crm_orders(days_back=30, domain=DOMAIN, api_key=API_KEY):
    """
    Парсит заказы из SalesDrive за указанный период (в днях).
    Оставляет только те заказы, чьи организации и статусы присутствуют в словарях (по crm_code).
    """
    url = f"https://{domain}.salesdrive.me/api/order/list/"
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }

    # 1. Вычисляем дату начала выгрузки (сегодня минус days_back дней)
    date_from = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    # 2. Извлекаем только первые коды (crm_code) для формирования "белых списков"
    allowed_org_ids = {org["crm_code"] for org in ORGANIZATIONS_MAP.values()}
    allowed_status_ids = {status["crm_code"] for status in STATUSES_MAP.values()}
    allowed_payment_ids = {p["crm_code"] for p in PAYMENT_METHODS_MAP.values()}
    
    # Базовые параметры API запроса
    params = {
        "limit": 100,
        "filter[orderTime][from]": date_from
    }
    
    filtered_orders = []
    page = 1

    print(f"🔄 Загрузка заказов с CRM {date_from}...")

    # 3. Цикл пагинации для сбора всех страниц
    while True:
        params["page"] = page
        try:
            response = requests.get(url, headers=headers, params=params)
            
            # Проверка на ошибки (например, неверный ключ)
            if response.status_code != 200:
                print(f"❌ Ошибка API SalesDrive: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            orders = data.get('data', [])
            
            if not orders:
                break # Если заказов больше нет, выходим из цикла
            
            # 4. Проверяем каждый заказ: есть ли его параметры в наших "белых списках"
            for order in orders:
                org_id = order.get('organizationId')
                status_id = order.get('statusId')
                payment_id = order.get('payment_method', "error")
                
                # Строгое условие: совпадение и по организации, и по статусу
                if (org_id in allowed_org_ids 
                    and status_id in allowed_status_ids
                    and payment_id in allowed_payment_ids):
                    filtered_orders.append(order)
            
            # Проверка метаданных на наличие следующих страниц
            meta = data.get('meta', {})
            total_pages = meta.get('totalPages', 1)
            
            if page >= total_pages:
                break
                
            page += 1

        except Exception as e:
            print(f"❌ Ошибка при выполнении запроса: {e}")
            break

    print(f"✅ Выгрузка завершена! Найдено подходящих заказов: {len(filtered_orders)}")
    return filtered_orders

def get_dilovod_orders(days_back=30, dilovod_token=DILOVOD_TOKEN):
    """
    Парсит заказы (documents.saleOrder) из Діловода за указанный период.
    """
    # 1. Вычисляем дату начала (сегодня минус days_back дней)
    # Діловод обычно понимает формат дат YYYY-MM-DD
    date_from = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    print(f"🔄 Загрузка заказов из Діловод с {date_from}...")

    # 2. Формируем пакет запроса согласно API Діловода
    packet = {
        "version": "0.25", 
        "key": dilovod_token, 
        "action": "request",
        "params": {
            "from": "documents.saleOrder",
            # Указываем, какие поля хотим получить. 
            # Можно добавлять нужные (например, сумму, контрагента и т.д.)
            "fields": {
                "id": "id",
                "date": "date",
                "number": "number",
                "state": "state",
                "sum": "amountAmount", # В Діловоде сумма документа обычно называется так, но можно уточнить в документации
                "remark": "remark"
            },
            # Фильтр: дата больше или равна date_from
            "filters": [
                {
                    "alias": "date", 
                    "operator": ">=", 
                    "value": date_from
                }
            ]
        }
    }

    # 3. Отправляем POST-запрос
    try:
        response = requests.post(
            DILOVOD_API_URL, 
            data={"packet": json.dumps(packet)}
        )
        
        # Проверяем на ошибки HTTP
        if response.status_code != 200:
            print(f"❌ Ошибка соединения с Діловод: {response.status_code}")
            return []
            
        result = response.json()
        
        # 4. Обработка ответа
        # Если API вернуло словарь с ключом 'error'
        if isinstance(result, dict) and 'error' in result:
            print(f"❌ Ошибка Діловода: {result['error']}")
            return []
            
        # Успешный запрос обычно возвращает список словарей (записей)
        if isinstance(result, list):
            print(f"✅ Готово! Найдено заказов в Діловоде: {len(result)}")
            return result
            
        return []

    except Exception as e:
        print(f"❌ Критическая ошибка при запросе к Діловод: {e}")
        return []

def get_missing_orders(crm_orders, dilovod_orders):
    """
    Сравнивает списки заказов CRM и Діловода.
    Возвращает список заказов, которые есть в CRM, но отсутствуют в Діловоде.
    """
    print("🔄 Начинаем сверку баз...")
    
    # 1. Собираем все ID заказов CRM, которые уже есть в Діловоде
    dilovod_crm_ids = set()
    
    for d_order in dilovod_orders:
        remark = d_order.get('remark', '')
        
        # Ищем шаблон: открывающая скобка [, затем любые цифры, затем закрывающая ]
        match = re.search(r'\[(\d+)\]', str(remark))
        
        if match:
            # Извлекаем найденные цифры (ID заказа из SalesDrive)
            try:
                extracted_id = int(match.group(1))
                dilovod_crm_ids.add(extracted_id)
            except ValueError:
                continue

    # 2. Ищем заказы из CRM, которых нет в множестве dilovod_crm_ids
    missing_orders = []
    
    for crm_order in crm_orders:
        try:
            # Берем ID заказа из CRM (безопасное приведение к int)
            crm_id = int(crm_order.get('id', 0))
        except ValueError:
            print(f"⚠️ Ошибка типа ID в заказе CRM: {crm_order.get('id')}")
            continue
            
        # Если этого ID нет в Діловоде, добавляем в список потеряшек
        if crm_id and crm_id not in dilovod_crm_ids:
            missing_orders.append(crm_order)
            
    print(f"✅ Сверка завершена! Найдено {len(missing_orders)} заказов, которых нет в Діловоде.")
    return missing_orders

def process_missing_orders(missing_orders):
    """
    Проходится по списку недостающих заказов, фильтрует их по статусу CRM 
    и отправляет разрешенные на создание в Діловод.
    """
    # Множество статусов SalesDrive, которые мы строго игнорируем
    
    created_count = 0

    print("🚀 Начинаем перенос недостающих заказов в Діловод...")

    for order in missing_orders:
        order_start = time.time() # Замер начала обработки заказа
        order_id = order.get('id')
        
        # Безопасное извлечение статуса CRM (защита от строковых значений)
        try:
            status_id = int(order.get('statusId', 0))
        except ValueError:
            print(f"⚠️ Ошибка типа статуса в заказе CRM №{order_id}")
            continue

        # 1. Проверяем, не входит ли статус в наш "черный список"
        if status_id in ignored_statuses:
            print(f"⏩ Пропуск заказа №{order_id} (статус {status_id} в списке исключений)")
            continue

        # 2. Если статус разрешен, запускаем процесс создания
        print(f"➕ Отправка заказа №{order_id} статус {status_id} в Діловод...")
        
        new_dilovod_id = send_to_dilovod(order)
        
        if new_dilovod_id:
            print(f"✅ Заказ №{order_id} успешно перенесен! (ID Діловод: {new_dilovod_id})")
            created_count += 1
            mark_order_in_salesdrive(order_id, "id_23")
            
        else:
            print(f"❌ Ошибка при создании заказа №{order_id}")
            mark_order_in_salesdrive(order_id, "id_24")
        order_end = time.time() # Замер конца
        print(f"⏱️ Заказ №{order_id} обработан за {order_end - order_start:.3f} сек.")
    print(f"🎉 Процесс завершен. Успешно перенесено заказов: {created_count}")

def get_dilovod_code(map_dict, crm_id):
    """
    Вспомогательная функция. 
    Ищет в словаре (ORGANIZATIONS_MAP или STATUSES_MAP) нужный code_2 (ID Діловода) 
    на основе code_1 (ID SalesDrive).
    """
    for name, data in map_dict.items():
        if data.get("crm_code") == crm_id:
            return data.get("dil_code")
    return None

def send_to_dilovod(crm_order):
    """
    Создает новый заказ покупателя в Діловоде на основе данных из SalesDrive.
    """
    order_id = crm_order.get('id')
    
    # 1. Безопасное извлечение ID из CRM
    try:
        org_id_crm = int(crm_order.get('organizationId', 0))
        status_id_crm = int(crm_order.get('statusId', 0))
    except ValueError:
        print(f"❌ Ошибка: Неверный формат ID организации или статуса в заказе {order_id}")
        return False

    # 2. Ищем соответствующие ID для Діловода
    firm_code = get_dilovod_code(ORGANIZATIONS_MAP, org_id_crm)
    state_code = get_dilovod_code(STATUSES_MAP, status_id_crm)

    if not firm_code:
        print(f"❌ Ошибка: Для организации CRM={org_id_crm} не найден Діловод ID в словаре.")
        return False

    if not state_code:
        print(f"❌ Ошибка: Для статуса CRM={status_id_crm} не найден Діловод ID в словаре. Заказ {order_id} не перенесен.")
        return False


    

    # Достаем телефон
    phone = ''
    primary_contact = crm_order.get('primaryContact')
    if isinstance(primary_contact, dict):
        phone_list = primary_contact.get('phone', [])
        # Так как телефон лежит в списке (например, ["380969610444"]), берем первый элемент
        if isinstance(phone_list, list) and len(phone_list) > 0:
            phone = str(phone_list[0])
    
    # Достаём ТТН
    ttn = ''
    delivery_data = crm_order.get('ord_delivery_data')
    if isinstance(delivery_data, list) and len(delivery_data) > 0:
        first_delivery = delivery_data[0]
        if isinstance(first_delivery, dict):
            ttn = first_delivery.get('trackingNumber', '')


    # 3. Формируем список товаров
    dilovod_goods = []
    for prod in crm_order.get('products', []):
        sku = prod.get('sku')
        if not sku: 
            continue
            
        prod_id = find_product_in_dilovod(sku) 
        
        if prod_id:
            amount = prod.get('amount', 1)
            price = prod.get('price', 0)
            row_sum = amount * price
            
            dilovod_goods.append({
                "good": prod_id, 
                "qty": amount,
                "price": price, 
                "unit": "1103600000000001", 
                "amountCur": row_sum, 
                "priceAmount": row_sum
            })

    if not dilovod_goods:
        print(f"⚠️ В заказе {order_id} нет товаров, найденных в Діловоде. Пропускаем создание.")
        return False

    # 4. Формируем JSON-пакет данных для Діловода
    packet = {
        "version": "0.25", 
        "key": DILOVOD_TOKEN, 
        "action": "saveObject",
        "params": {
            "header": {
                "id": "documents.saleOrder", 
                "date": crm_order.get('orderTime'),
                "remark": f"[{order_id}]",
                "firm": firm_code,
                "state": state_code,
                "currency": "1101200000001001",
                "person": "1100100000000001",
                "storage": "1100700000000001",
                "deliveryMethod_forDel": "1110400000001001",   
                "details": phone,                 
                "deliveryRemark_forDel": ttn            
            },
            "tableParts": {"tpGoods": dilovod_goods}
        }
    }

    # 5. Отправляем POST-запрос в Діловод
    try:
        response = requests.post(DILOVOD_API_URL, data={"packet": json.dumps(packet)})
        res = response.json()
        
        if isinstance(res, dict) and 'id' in res: 
            return res['id']
        elif isinstance(res, list) and len(res) > 0: 
            return res[0].get('id')
        elif isinstance(res, dict) and 'error' in res:
            print(f"❌ Ошибка Діловода при создании заказа {order_id}: {res['error']}")
            return False
            
        return False
    except Exception as e:
        print(f"❌ Критическая ошибка соединения при отправке заказа {order_id}: {e}")
        return False

def find_product_in_dilovod(sku):
    packet = {
        "version": "0.25", "key": DILOVOD_TOKEN, "action": "request",
        "params": {
            "from": "catalogs.goods",
            "fields": {"id": "id", "productNum": "productNum"},
            "filters": [{"alias": "productNum", "operator": "=", "value": str(sku)}]
        }
    }
    try:
        response = requests.post(DILOVOD_API_URL, data={"packet": json.dumps(packet)})
        result = response.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0].get('id')
    except:
        return None
    return None

def mark_order_in_salesdrive(order_id, mark_code):
    """
    Обновляет кастомное поле 'dilovod' в SalesDrive.
    mark_code: "id_23" (Так) или "id_24" (Ні).
    """
    url = f"https://{DOMAIN}.salesdrive.me/api/order/update/"
    headers = {"X-Api-Key": API_KEY}
    
    payload = {"id": str(order_id), "data[dilovod]": str(mark_code)}
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        if response.status_code in [200, 201]:
            print(f"☑️ Заказ {order_id} отмечен в SalesDrive (dilovod = {mark_code})")
            return True
        else:
            print(f"⚠️ Ошибка отметки SalesDrive: {response.text[:100]}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def update_dilovod_status(dilovod_id, new_state_code):
    """
    Обновляет статус (state) существующего документа в Діловоде.
    """
    packet = {
        "version": "0.25", 
        "key": DILOVOD_TOKEN, 
        "action": "saveObject",
        "params": {
            "header": {
                "id": dilovod_id, # Передаем уникальный ID документа (например, 110910...)
                "state": new_state_code
            }
        }
    }
    
    try:
        response = requests.post(DILOVOD_API_URL, data={"packet": json.dumps(packet)})
        res = response.json()
        
        if isinstance(res, dict) and 'error' in res:
            print(f"❌ Ошибка Діловода при обновлении статуса: {res['error']}")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Критическая ошибка при обновлении статуса: {e}")
        return False

def sync_order_statuses(crm_orders, dil_orders):
    """
    Сверяет статусы заказов. Если статус в CRM изменился, обновляет его в Діловоде.
    """
    print("🔄 Начинаем синхронизацию статусов...")
    updated_count = 0

    # 1. Создаем словарь для быстрого поиска заказов Діловода по CRM ID
    dil_dict = {}
    for d_order in dil_orders:
        remark = d_order.get('remark', '')
        
        # Ищем ID из SalesDrive в квадратных скобках
        match = re.search(r'\[(\d+)\]', str(remark))
        if match:
            crm_id = int(match.group(1))
            dil_dict[crm_id] = d_order

    # 2. Перебираем заказы из CRM и сверяем статусы
    for crm_order in crm_orders:
        try:
            crm_id = int(crm_order.get('id', 0))
            current_crm_status = int(crm_order.get('statusId', 0))
        except ValueError:
            continue
            
        # Если заказ уже существует в Діловоде
        if crm_id in dil_dict:
            dil_order = dil_dict[crm_id]
            current_dil_status = dil_order.get('state')
            
            # Узнаем, какой статус должен быть в Діловоде согласно нашему словарю
            target_dil_status = get_dilovod_code(STATUSES_MAP, current_crm_status)
            
            # Если статус найден в словаре и он отличается от текущего в Діловоде
            if target_dil_status and target_dil_status != current_dil_status:
                dilovod_doc_id = dil_order.get('id')
                
                print(f"🔄 Заказ {crm_id}: смена статуса в Діловоде на '{target_dil_status}'...")
                
                # Вызываем функцию обновления
                if update_dilovod_status(dilovod_doc_id, target_dil_status):
                    print(f"✅ Статус заказа {crm_id} успешно обновлен!")
                    updated_count += 1
                else:
                    print(f"⚠️ Не удалось обновить статус заказа {crm_id}.")

    print(f"🎉 Синхронизация завершена. Обновлено статусов: {updated_count}")
        
if __name__ == "__main__":
    while True:
        crm_orders = get_crm_orders()
        dil_orders = get_dilovod_orders()
        missing_orders = get_missing_orders(crm_orders, dil_orders)
        
        process_missing_orders(missing_orders)
        
        sync_order_statuses(crm_orders, dil_orders)
        
        time.sleep(30)

    
        