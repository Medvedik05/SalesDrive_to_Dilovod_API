import os
import json
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения (.env)
load_dotenv()

API_KEY = os.getenv("API_KEY")
DOMAIN = os.getenv("DOMAIN")

def get_order_by_id(order_id):
    """
    Делает запрос к API SalesDrive и выводит всю информацию о заказе по его ID.
    """
    # URL для получения списка/информации о заказе
    url = f"https://{DOMAIN}.salesdrive.me/api/order/list/"
    
    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Фильтруем конкретный заказ по его ID
    params = {
        "filter[id]": order_id
    }
    
    try:
        print("⏳ Запрос данных для заказа №{order_id} из SalesDrive...")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"❌ Ошибка API SalesDrive: {response.status_code} - {response.text}")
            return
            
        data = response.json()
        orders = data.get('data', [])
        
        if not orders:
            print(f"⚠️ Заказ с ID {order_id} не найден в SalesDrive.")
            return
            
        # Берем первый найденный заказ
        order = orders[0]
        
        # Выводим красиво отформатированный JSON
        print("\n" + "="*40)
        print(f"📦 Информация по заказу №{order_id}:")
        print("="*40)
        print(json.dumps(order, indent=4, ensure_ascii=False))
        print("="*40)
        
    except Exception as e:
        print(f"❌ Критическая ошибка при запросе: {e}")

if __name__ == "__main__":
    # Задаем ID заказа, который нужно проверить (можешь поменять на нужный)
    target_order_id = 102
    
    if target_order_id:
        get_order_by_id(target_order_id)
    else:
        print("⚠️ ID не введен.")