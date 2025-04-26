import argparse
import json
import os
import time
from datetime import datetime

import requests
import schedule
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Загрузка переменных из .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HISTORY_FILE = "history.json"  # Файл для сохранения истории

# Если беда с токенами ТГ, то крашимся
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы!")

# --- Загрузка и сохранение истории ---
def load_history():
    """Загружает историю из файла."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(data):
    """Сохраняет историю в файл."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Загрузка директории и имени файла
def parse_args():
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Парсер страниц с фигурками.")
    parser.add_argument("-d", "--dir", default=".", help="Директория с файлом данных")
    parser.add_argument("-f", "--file", default="statues.txt", help="Имя файла с данными")
    return parser.parse_args()

args = parse_args()
input_path = f"{args.dir}/{args.file}"

# Читаем файл со ссылочками на фигурки
def read_input_file():
    # Читаем ссылки из файла (одна строка — одна ссылка)
    with open(input_path, "r", encoding="utf-8") as file:
        urls = [line.strip() for line in file if line.strip()]

    return urls

input_data = read_input_file()

# Словарь для хранения последних состояний
product_history = load_history()

# Отправляем нотификацию мне в ЛС
def send_telegram_notification(message):
    """Отправка уведомления в Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print(f"Telegram response status code: {response.status_code}, Reason: {response.text}")


def parse_description_block(description_block):
    """Универсальный парсер для блока описания"""
    description_data = {}

    if not description_block:
        return description_data

    description_elements = description_block.find_all(string=True, recursive=True)
    # Ищем все элементы с текстом (рекурсивно, включая вложенные теги)
    for element in description_elements:
        # Пропускаем пустые строки и текст из пустых тегов
        if not element.strip() or (element.parent and not element.parent.get_text(strip=True)):
            continue

        text = element.strip()

        # Обрабатываем только строки с ":" (ключ-значение)
        if ":" in text:
            # Разделяем по первому ":", оставляя остальные в значении
            key, value = text.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Объединяем дубликаты ключей (если есть)
            if key in description_data:
                description_data[key] += f"; {value}"  # или другой разделитель
            else:
                description_data[key] = value
        else:
            # Для текста без ":" сохраняем с общим ключом "Note"
            if "Note" not in description_data:
                description_data["Note"] = []
            description_data["Note"].append(text)

    return description_data

# Получаем инфо по фигурке.
def parse_product_info(url):
    """Парсит 'Product Phase' и 'Est Released Time' со страницы."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Ищем блок, содержащий "Product Phase:"
        phase_block = soup.find(lambda tag: tag.text.strip().startswith("Product Phase:"))
        if phase_block:
            phase_text = ' '.join(phase_block.stripped_strings)  # Объединяет текст из всех вложенных тегов
        else:
            phase_text = None

        # Аналогично для "Est Released Time:"
        released_time_block = soup.find(lambda tag: tag.text.strip().startswith("Est Released Time:"))
        if released_time_block:
            released_time_text = ' '.join(released_time_block.stripped_strings)
        else:
            released_time_text = None

        # Парсим блок с описанием
        description_block = soup.find("div", id="tab-description")
        description_data = parse_description_block(description_block)

        return {
            "phase": phase_text,
            "released_time": released_time_text,
            "description": description_data,
            "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"⚠ Ошибка при парсинге {url}: {str(e)}")
        return None


def check_products():
    """Основная функция проверки изменений."""
    print(f"\n🔍 Проверка {datetime.now().strftime('%d.%m %H:%M:%S')}")

    for url in input_data:
        current_info = parse_product_info(url)
        if not current_info:
            continue

        # Загружаем предыдущие данные (если есть)
        last_info = product_history.get(url, {})

        # Проверяем изменения
        phase_changed = current_info["phase"] != last_info.get("phase")
        time_changed = current_info["released_time"] != last_info.get("released_time")

        # Проверяем изменения в описании
        description_changes = {}
        if "description" in current_info:
            for key, value in current_info["description"].items():
                if key not in last_info.get("description", {}) or last_info["description"][key] != value:
                    description_changes[key] = {
                        "old": last_info.get("description", {}).get(key, "неизвестно"),
                        "new": value
                    }

        if phase_changed or time_changed or description_changes:
            product_history[url] = current_info  # Обновляем историю
            print(f"Изменение обнаружено!")

            # Если первый запуск - пускать нотификацию не надо.
            if last_info == {}:
                continue

            # Формируем сообщение
            message_parts = [
                f"🔄 *Изменение статуса!*",
                f"• Товар: {url}"
            ]

            if phase_changed:
                message_parts.append(
                    f"• Статус: `{last_info.get('phase', 'неизвестно')}` → `{current_info['phase']}`"
                )

            if time_changed:
                message_parts.append(
                    f"• Время выхода: `{last_info.get('released_time', 'неизвестно')}` → `{current_info['released_time']}`"
                )

            for key, change in description_changes.items():
                message_parts.append(
                    f"• {key}: `{change['old']}` → `{change['new']}`"
                )

            message = "\n".join(message_parts)
            send_telegram_notification(message)
            print(f"📢 Отправлено уведомление для {url}")

    save_history(product_history)
    print(f"Проверка закончена.")


def run_scheduler():
    print("🔄 Скрипт запущен. Ожидание изменений...")
    schedule.every(6).hours.do(check_products)

    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверка каждую минуту


if __name__ == "__main__":
    check_products()  # Первая проверка сразу
    run_scheduler()