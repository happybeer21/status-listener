import requests
from bs4 import BeautifulSoup
import re
from collections import defaultdict


def parse_input_file(file_path):
    """Чтение файла и извлечение URL с группировкой по месяцам."""
    month_data = defaultdict(list)  # Словарь для хранения данных по месяцам
    current_month = None

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue

            # Проверяем, является ли строка датой (например, "04.2025")
            if re.match(r'^\d{2}\.\d{4}$', line):
                current_month = line
                continue

            # Извлекаем URL из строк вида "[1$] Название: https://example.com"
            match = re.match(r'^\d+\)\s+\[\d+\$\]\s+.+?:\s+(https?://\S+)', line)
            if match and current_month:
                url = match.group(1)
                month_data[current_month].append(url)

    return month_data


def check_product_phase(url):
    """Проверяет, есть ли на странице фраза 'Product Phase: released'."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Проверка на ошибки HTTP

        soup = BeautifulSoup(response.text, 'html.parser')
        return "Product Phase: released" in soup.get_text()
    except Exception as e:
        print(f"⚠ Ошибка при проверке {url}: {str(e)}")
        return False


def main():
    input_file = "input.txt"  # Путь к вашему файлу
    output_file = "results.txt"

    # Парсим входной файл
    month_data = parse_input_file(input_file)

    # Проверяем каждый URL и сохраняем результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        for month, urls in month_data.items():
            f.write(f"{month}\n")
            print(f"🔍 Проверяем месяц: {month}")

            for url in urls:
                is_released = check_product_phase(url)
                status = "✅ Released" if is_released else "❌ Not Released"
                f.write(f"{url} - {status}\n")
                print(f"   {url} - {status}")

            f.write("\n")  # Разделитель между месяцами


if __name__ == "__main__":
    main()