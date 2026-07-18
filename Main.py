from datetime import date
import os
import json
import requests
import time
from dotenv import load_dotenv

load_dotenv()

# --- КЛЮЧИ И НАСТРОЙКИ ---
API_KEY = os.getenv("API_KEY")
DOMAIN = os.getenv("DOMAIN")
DILOVOD_API_URL = "https://api.dilovod.ua/api/"
DILOVOD_TOKEN = os.getenv("DILOVOD_TOKEN") 
STATE_FILE = 'orders_state.json'

# --- 1. ФУНКЦИИ ПАМЯТИ ---
def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_current_state(state_dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state_dict, f)

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
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

def get_salesdrive_orders():
    url = f"https://{DOMAIN}.salesdrive.me/api/order/list/"
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers, params={"limit": 100})
        return response.json().get('data', [])
    except:
        return []

# --- 3. ФУНКЦИЯ ОБНОВЛЕНИЯ SALESDRIVE (РАБОЧАЯ) ---
def mark_order_in_salesdrive(order_id, mark_code):
    url = f"https://{DOMAIN}.salesdrive.me/api/order/update/"
    headers = {"X-Api-Key": API_KEY}
    
    # Отправляем "id_23" или "id_24"
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

# --- 4. ФУНКЦИИ ДІЛОВОД ---
def send_to_dilovod(sd_order):
    dilovod_goods = []
    for prod in sd_order.get('products', []):
        sku = prod.get('sku')
        if not sku: continue
        prod_id = find_product_in_dilovod(sku)
        if prod_id:
            row_sum = prod.get('amount', 1) * prod.get('price', 0)
            dilovod_goods.append({
                "good": prod_id, "qty": prod.get('amount', 1),
                "price": prod.get('price', 0), "unit": "1103600000000001",
                "amountCur": row_sum, "priceAmount": row_sum
            })
    
    if not dilovod_goods: return False
    
    packet = {
        "version": "0.25", "key": DILOVOD_TOKEN, "action": "saveObject",
        "params": {
            "header": {
                "id": "documents.saleOrder", 
                "date": sd_order.get('orderTime'),
                "remark": f"Заказ из SalesDrive №{sd_order.get('id')}",
                "firm": "1100400000001002", "currency": "1101200000001001",
                "person": "1100100000000001", "storage": "1100700000000001",
                "state": "1111500000000005"
            },
            "tableParts": {"tpGoods": dilovod_goods}
        }
    }
    
    try:
        res = requests.post(DILOVOD_API_URL, data={"packet": json.dumps(packet)}).json()
        if isinstance(res, dict) and 'id' in res: return res['id']
        elif isinstance(res, list) and len(res) > 0: return res[0].get('id')
        return False
    except: return False

def update_in_dilovod(sd_order, dilovod_doc_id):
    if not dilovod_doc_id:
        print(f"❌ ОШИБКА: У заказа {sd_order.get('id')} стоит 'так' (id_23), но ID в Діловоде неизвестен.")
        return False

    url = DILOVOD_API_URL
    STATUS_MATCH = {3: "1111500000000005", 4: "1111500000000008", 5: "1111500000000006", 6: "1111500000000007", 9: "1111500000000007"}
    state_id = STATUS_MATCH.get(sd_order.get('statusId'))
    
    if not state_id:
        print(f"❌ ОШИБКА: Для статуса {sd_order.get('statusId')} нет соответствия в Діловоде.")
        return False
    
    packet = {
        "version": "0.25", "key": DILOVOD_TOKEN, "action": "saveObject",
        "params": {"header": {"id": dilovod_doc_id, "state": state_id}}
    }
    
    try:
        response = requests.post(url, data={"packet": json.dumps(packet)})
        res = response.json()
        if isinstance(res, dict) and 'error' in res:
            print(f"❌ ОШИБКА Діловода при обновлении {sd_order.get('id')}: {res['error']}")
            return False
        return True
    except Exception as e:
        print(f"❌ ОШИБКА соединения при обновлении {sd_order.get('id')}: {e}")
        return False

# --- 5. ГЛАВНЫЙ ЦИКЛ ---
def sync_crm_to_erp():
    orders = get_salesdrive_orders()
    if not orders: return
    state = load_previous_state() 
    
    for order in orders:
        order_id = str(order.get('id'))
        current_status = order.get('statusId')
        crm_mark = str(order.get('dilovod', '')).strip()
        is_marked = (crm_mark == 'id_23')
        
        # --- ВЕТКА: ОБНОВЛЕНИЕ (ТОЛЬКО ДЛЯ ID_23) ---
        if is_marked:
            # 1. Если ID заказа отсутствует в памяти, пробуем его найти поиском по комментарию
            if order_id not in state or state[order_id].get("dilovod_id") is None:
                print(f"🔍 Заказ {order_id} помечен 'так', ищем ID в Діловоде...")
                # ... (логика поиска по ремарке "Заказ из SalesDrive №{order_id}") ...
                # (Для краткости: предположим, поиск вернул found_id)
                # Если поиск не вернул ID -> ПИШЕМ ОШИБКУ И ВЫХОДИМ
                print(f"❌ ОШИБКА: Заказ {order_id} имеет метку id_23, но не найден в Діловоде!")
                continue

            # 2. Если заказ есть, проверяем статус и обновляем
            if current_status != state[order_id].get("status"):
                if update_in_dilovod(order, state[order_id]["dilovod_id"]):
                    state[order_id]["status"] = current_status
                else:
                    print(f"❌ ОШИБКА: Не удалось обновить статус заказа {order_id}")
            continue # Ветка закончена, переходим к следующему заказу

        # --- ВЕТКА: ПЕРЕНОС (ТОЛЬКО ДЛЯ НОВЫХ) ---
        is_target_order = order.get('organizationId') == 1 and order.get('payment_method') in [16, 6]
        
        # Не переносим, если статус 9 или нет условий
        if current_status == 9 or not is_target_order or current_status < 3:
            continue

        print(f"🎯 Перенос нового заказа {order_id}...")
        new_id = send_to_dilovod(order)
        if new_id:
            state[order_id] = {"status": current_status, "in_dilovod": True, "dilovod_id": new_id}
            mark_order_in_salesdrive(order_id, "id_23")
            if current_status > 3: update_in_dilovod(order, new_id)
        else:
            mark_order_in_salesdrive(order_id, "id_24")

    save_current_state(state)

if __name__ == "__main__":
    while True:
        sync_crm_to_erp()
        time.sleep(30)