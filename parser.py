import argparse
import os
import re
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

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы!")

# Загрузка директории и имени файла
def parse_args():
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Парсер страниц с фигурками.")
    parser.add_argument("-d", "--dir", default=".", help="Директория с файлом данных")
    parser.add_argument("-f", "--file", default="statues.txt", help="Имя файла с данными")
    return parser.parse_args()

args = parse_args()
input_path = f"{args.dir}/{args.file}"

# --- Чтение файла ---
def read_input_file():
    # Читаем ссылки из файла (одна строка — одна ссылка)
    with open(input_path, "r", encoding="utf-8") as file:
        urls = [line.strip() for line in file if line.strip()]

    return urls

input_data = read_input_file()

# Словарь для хранения последних состояний {url: last_phase}
product_history = {}

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

        return {
            "phase": phase_text,
            "released_time": released_time_text
        }
    except Exception as e:
        print(f"⚠ Ошибка при парсинге {url}: {str(e)}")
        return None


def check_products():
    """Основная функция проверки изменений."""
    print(f"\n🔍 Проверка {datetime.now().strftime('%d.%m %H:%M')}")

    for url in input_data:
        current_info = parse_product_info(url)
        if not current_info:
            continue

        # Загружаем предыдущие данные (если есть)
        last_info = product_history.get(url, {})

        # Проверяем изменения
        phase_changed = current_info["phase"] != last_info.get("phase")
        time_changed = current_info["released_time"] != last_info.get("released_time")

        if phase_changed or time_changed:
            product_history[url] = current_info  # Обновляем историю

            # Формируем сообщение
            message = (
                f"🔄 *Изменение статуса!*\n"
                f"• Товар: {url}\n"
                f"• Новый статус: `{current_info['phase']}`\n"
                f"• Новое время: `{current_info['released_time']}`\n"
                f"• Предыдущий статус: `{last_info.get('phase', 'неизвестно')}`\n"
                f"• Предыдущее время: `{last_info.get('released_time', 'неизвестно')}`"
            )
            send_telegram_notification(message)
            print(f"📢 Отправлено уведомление для {url}")


def run_scheduler():
    """Запускает проверку каждые 4 часа."""
    print("🔄 Скрипт запущен. Ожидание изменений...")
    schedule.every(4).hours.do(check_products)

    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверка каждую минуту


if __name__ == "__main__":
    check_products()  # Первая проверка сразу
    run_scheduler()